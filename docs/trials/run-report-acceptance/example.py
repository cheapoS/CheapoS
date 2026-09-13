"""Runnable minimal example, using synthetic saved data (never personal history)."""
from contract import task


def make_example():
    from cheapos.run_report import render_run_report
    return render_run_report(task())


if __name__ == '__main__':
    print(make_example(), end='')
