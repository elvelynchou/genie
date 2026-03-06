#!/bin/bash
export DISPLAY=:20.0
export XAUTHORITY=/home/elvelyn/.Xauthority
export HOME=/home/elvelyn

# Clean up any potential locks
rm -rf /etc/myapp/genie/profiles/geclibot_profile/SingletonLock
rm -rf /etc/myapp/genie/profiles/geclibot_profile/lock
rm -rf /etc/myapp/genie/profiles/geclibot_profile/.parentlock

echo "Starting stealth_browser via Agent logic..."
/etc/myapp/genie/venv/bin/python3 -c "
import asyncio
import os
import sys
sys.path.append('/etc/myapp/genie/src')
from agents.registry import registry
from agents.common.browser_agent import BrowserAgent

async def run():
    try:
        registry.register_agent(BrowserAgent())
        agent = registry.get_agent('stealth_browser')
        print('Agent loaded, executing...')
        # We use a fresh profile 'test_gui' to rule out locking issues
        result = await agent.execute(
            'test_gui_task', 
            engine='camoufox', 
            profile='test_gui', 
            headless=False, 
            keep_open=True, 
            actions=[{'action': 'goto', 'params': {'url': 'https://x.com/login'}}]
        )
        print(f'Execution status: {result.status}')
        if result.status == 'FAILED':
            print(f'Errors: {result.errors}')
        await asyncio.sleep(600)
    except Exception as e:
        print(f'Exception: {e}')

asyncio.run(run())
"
