"""Optional OS credential storage. Never fall back to plaintext files."""

import ctypes as ct
import hashlib
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path


class CredentialError(ValueError):
    pass


class CredentialStore:
    def __init__(self, directory):
        self.scope = hashlib.sha256(str(Path(directory).resolve()).encode()).hexdigest()
        self.backend = 'macOS Keychain' if sys.platform == 'darwin' else 'Secret Service' if sys.platform.startswith('linux') and shutil.which('secret-tool') else None

    def _account(self, endpoint):
        # Deliberately bind to the exact configured URL, just like connection authority.
        return self.scope + ':' + hashlib.sha256(endpoint.encode()).hexdigest()

    def _operate(self, action, endpoint, value=None):
        if not self.backend:
            raise CredentialError('Secure credential storage is unavailable. Use a session-only key or CHEAPOS_GATEWAY_API_KEY.')
        try:
            if self.backend == 'macOS Keychain':
                return MacKeychain().operate(action, self._account(endpoint), value)
            args = ['secret-tool', {'get':'lookup', 'set':'store', 'delete':'clear'}[action]]
            if action == 'set': args += ['--label=cheapoS OmniRoute client key']
            args += ['application', 'cheapoS', 'account', self._account(endpoint)]
            result = subprocess.run(args, input=value if action == 'set' else '', text=True,
                                    capture_output=True, timeout=15)
            if result.returncode == 0:
                return result.stdout.rstrip('\n') if action == 'get' else None
            if result.returncode == 1 and not result.stderr.strip() and action in {'get', 'delete'}:
                return None  # No matching item.
            raise CredentialError('Secure credential storage could not be accessed. Unlock your credential store and try again, or use a session-only key.')
        except (OSError, subprocess.SubprocessError, UnicodeError):
            # Never expose subprocess output, arguments, or OS exception data containing a key.
            raise CredentialError('Secure credential storage could not be accessed. Unlock your credential store and try again, or use a session-only key.') from None

    def get(self, endpoint):
        return self._operate('get', endpoint)

    def set(self, endpoint, value):
        self._operate('set', endpoint, value)

    def delete(self, endpoint):
        self._operate('delete', endpoint)


class MacKeychain:
    """Small SecItem bridge; secrets never appear in process arguments or temp files."""
    def __init__(self):
        self.cf = ct.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        self.sec = ct.CDLL('/System/Library/Frameworks/Security.framework/Security')
        signatures = {
            'CFStringCreateWithCString': (ct.c_void_p, [ct.c_void_p, ct.c_char_p, ct.c_uint32]),
            'CFDataCreate': (ct.c_void_p, [ct.c_void_p, ct.c_char_p, ct.c_long]),
            'CFDictionaryCreate': (ct.c_void_p, [ct.c_void_p, ct.POINTER(ct.c_void_p), ct.POINTER(ct.c_void_p), ct.c_long, ct.c_void_p, ct.c_void_p]),
            'CFDataGetLength': (ct.c_long, [ct.c_void_p]),
            'CFDataGetBytePtr': (ct.c_void_p, [ct.c_void_p]),
            'CFRelease': (None, [ct.c_void_p]),
        }
        for name, (result, arguments) in signatures.items():
            function = getattr(self.cf, name)
            function.restype, function.argtypes = result, arguments
        for name, arguments in {
            'SecItemCopyMatching':[ct.c_void_p, ct.POINTER(ct.c_void_p)],
            'SecItemAdd':[ct.c_void_p, ct.POINTER(ct.c_void_p)],
            'SecItemUpdate':[ct.c_void_p, ct.c_void_p],
            'SecItemDelete':[ct.c_void_p],
        }.items():
            function = getattr(self.sec, name)
            function.restype, function.argtypes = ct.c_int32, arguments

    def constant(self, name):
        return ct.c_void_p.in_dll(self.sec, name).value

    @contextmanager
    def dictionary(self, values):
        owned, keys, refs = [], [], []
        try:
            for key, value in values.items():
                keys.append(self.constant(key))
                if isinstance(value, str):
                    ref = self.cf.CFStringCreateWithCString(None, value.encode(), 0x08000100)
                    owned.append(ref)
                elif isinstance(value, bytes):
                    ref = self.cf.CFDataCreate(None, value, len(value))
                    owned.append(ref)
                else:
                    ref = value
                if not ref: raise CredentialError('Could not prepare a Keychain request.')
                refs.append(ref)
            array = ct.c_void_p * len(keys)
            # Objects remain owned here until the synchronous SecItem call completes.
            dictionary = self.cf.CFDictionaryCreate(None, array(*keys), array(*refs), len(keys), None, None)
            if not dictionary: raise CredentialError('Could not prepare a Keychain request.')
            owned.append(dictionary)
            yield dictionary
        finally:
            for ref in reversed(owned):
                if ref: self.cf.CFRelease(ref)

    def operate(self, action, account, value=None):
        query = {'kSecClass':self.constant('kSecClassGenericPassword'),
                 'kSecAttrService':'cheapoS OmniRoute', 'kSecAttrAccount':account,
                 'kSecUseAuthenticationUI':self.constant('kSecUseAuthenticationUIFail')}
        if action == 'get':
            query['kSecReturnData'] = ct.c_void_p.in_dll(self.cf, 'kCFBooleanTrue').value
            result = ct.c_void_p()
            with self.dictionary(query) as attributes:
                status = self.sec.SecItemCopyMatching(attributes, ct.byref(result))
            try:
                if status == -25300: return None  # errSecItemNotFound
                self.check(status)
                return ct.string_at(self.cf.CFDataGetBytePtr(result), self.cf.CFDataGetLength(result)).decode()
            finally:
                if result.value: self.cf.CFRelease(result)
        if action == 'delete':
            with self.dictionary(query) as attributes:
                status = self.sec.SecItemDelete(attributes)
            if status != -25300: self.check(status)
            return
        data = {'kSecValueData':value.encode()}
        with self.dictionary(query) as attributes, self.dictionary(data) as updates:
            status = self.sec.SecItemUpdate(attributes, updates)
        if status == -25300:
            with self.dictionary({**query, **data}) as attributes:
                status = self.sec.SecItemAdd(attributes, None)
        self.check(status)

    @staticmethod
    def check(status):
        if status:
            raise CredentialError('macOS Keychain could not be accessed. Unlock your login keychain and try again, or use a session-only key.')
