#!/bin/bash
export DISPLAY=:20.0
export XAUTHORITY=/home/elvelyn/.Xauthority
export HOME=/home/elvelyn
export PYTHONPATH=/etc/myapp/genie/src

echo "Launching Nodriver (Chrome) in GUI mode..."
/etc/myapp/genie/venv/bin/python3 -c "
import asyncio
import nodriver as uc

async def run():
    try:
        print('Starting browser...')
        browser = await uc.start(
            headless=False,
            browser_args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu']
        )
        print('Browser started, navigating...')
        page = browser.main_tab
        await page.get('https://x.com/login')
        print('Navigation complete. Keeping window open...')
        await asyncio.sleep(900)
    except Exception as e:
        print(f'Error: {e}')

asyncio.run(run())
"
