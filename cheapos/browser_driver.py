"""Owned Playwright subprocess. JSON lines in/out; no model-supplied JavaScript."""
import json
import sys
from collections import deque
from urllib.parse import urlsplit


def origin(url):
    value = urlsplit(url)
    if value.username or value.password:
        raise ValueError('URL credentials are not allowed')
    return value.scheme, value.hostname, value.port


def serve():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1280, 'height': 800},
                                      accept_downloads=False, service_workers='block')
        context.set_default_timeout(5000)
        context.set_default_navigation_timeout(10000)
        logs = deque(maxlen=100)
        allowed = None
        def route(request):
            try:
                permitted = origin(request.request.url) == allowed
            except ValueError:
                permitted = False
            if permitted:
                request.continue_()
            else:
                logs.append({'type': 'blocked_request', 'text': request.request.url[:1000]})
                request.abort()
        context.route('**/*', route)
        # WebSockets bypass HTTP routing. Permit only the displayed origin's socket.
        def socket_route(socket):
            value = origin(socket.url)
            if value == ('ws', allowed[1], allowed[2]):
                socket.connect_to_server()
            else:
                socket.close()
        context.route_web_socket('**/*', socket_route)
        page = context.new_page()
        context.on('page', lambda popup: popup.close() if popup != page else None)
        page.on('dialog', lambda dialog: dialog.dismiss())
        page.on('console', lambda message: logs.append({'type': message.type, 'text': message.text[:2000]}))
        page.on('pageerror', lambda error: logs.append({'type': 'pageerror', 'text': str(error)[:2000]}))
        page.on('requestfailed', lambda request: logs.append({'type': 'requestfailed', 'text': request.url[:1000]}))
        page.on('response', lambda response: logs.append({'type': 'http_error', 'text': response.url[:1000], 'status': response.status}) if response.status >= 400 else None)
        for line in sys.stdin:
            try:
                args = json.loads(line)
                action = args['action']
                if action == 'open':
                    allowed = origin(args['url'])
                    page.goto(args['url'], wait_until='domcontentloaded')
                elif action == 'navigate':
                    if origin(args['url']) != allowed:
                        raise ValueError('Navigation must stay on the authorized preview origin')
                    page.goto(args['url'], wait_until='domcontentloaded')
                elif action in {'click', 'fill', 'press', 'select'}:
                    locator = page.locator(args['selector'])
                    if action == 'click': locator.click()
                    elif action == 'fill': locator.fill(args['value'])
                    elif action == 'press': locator.press(args['value'])
                    else: locator.select_option(args['value'])
                elif action == 'viewport':
                    page.set_viewport_size({'width': args['width'], 'height': args['height']})
                elif action == 'screenshot':
                    page.screenshot(path=args['path'], full_page=False, timeout=5000)
                elif action != 'observe':
                    raise ValueError('Unsupported browser action')
                if origin(page.url) != allowed:
                    raise ValueError('Page left the authorized preview origin')
                selectors = 'button,input,select,textarea,a[href],[role=button]'
                controls = page.locator(selectors).evaluate_all("""nodes => nodes.map((el, index) => ({
                    index, tag: el.tagName.toLowerCase(), id: el.id, name: el.getAttribute('name'),
                    type: el.getAttribute('type'), label: (el.getAttribute('aria-label') || el.textContent || '').slice(0, 200),
                    visible: !!(el.getClientRects().length), disabled: !!el.disabled
                })).filter(el => el.visible).slice(0, 80)""")
                for control in controls:
                    control['selector'] = selectors + ' >> nth=' + str(control.pop('index'))
                result = {'url': page.url, 'title': page.title(), 'controls': controls,
                          'text': page.locator('body').inner_text(timeout=3000)[:12000],
                          'console': list(logs), 'viewport': page.viewport_size}
            except Exception as error:
                result = {'error': str(error)[:2000], 'console': list(logs)}
            print(json.dumps(result), flush=True)
        context.close()
        browser.close()


if __name__ == '__main__':
    try:
        serve()
    except Exception as error:
        print(json.dumps({'error': 'Browser runtime unavailable: ' + str(error)[:1500]}), flush=True)
