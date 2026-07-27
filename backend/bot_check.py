import asyncio
import os
import sys
import subprocess
import tempfile
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

async def run_diag():
    print(" BOT DETECTION DIAGNOSTICS")
    print("============================")
    
    chrome_path = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    temp_profile = os.path.join(tempfile.gettempdir(), 'diag_chrome_profile')
    debug_port = 9222
    
    chrome_cmd = [
        chrome_path,
        f'--remote-debugging-port={debug_port}',
        f'--user-data-dir={temp_profile}',
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-blink-features=AutomationControlled',
        'about:blank'
    ]
    
    proc = subprocess.Popen(chrome_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    await asyncio.sleep(3)
    
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(f'http://localhost:{debug_port}')
            context = browser.contexts[0]
            page = await context.new_page()
            
            # Inject stealth
            await Stealth().apply_stealth_async(page)
            
            # 1. Basic properties
            results = await page.evaluate("""() => {
                const getWebGL = () => {
                    const canvas = document.createElement('canvas');
                    const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
                    if (!gl) return { vendor: 'none', renderer: 'none' };
                    const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
                    return {
                        vendor: gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL),
                        renderer: gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL),
                    };
                };

                return {
                    webdriver: navigator.webdriver,
                    plugins: Array.from(navigator.plugins).map(p => p.name),
                    languages: navigator.languages,
                    chrome: !!window.chrome,
                    ua: navigator.userAgent,
                    cdc: !!Object.keys(window).find(k => k.includes('cdc_')),
                    hardware: navigator.hardwareConcurrency,
                    webgl: getWebGL(),
                    outerHeight: window.outerHeight,
                    outerWidth: window.outerWidth,
                };
            }""")
            
            print("\nBrowser Properties:")
            for k, v in results.items():
                print(f"  {k}: {v}")
                
            # 2. Check Cloudflare Turnstile state
            print("\nChecking Vatican Turnstile...")
            await page.goto("https://tickets.museivaticani.va/home", wait_until="networkidle")
            await page.wait_for_timeout(5000)
            
            # Check for turnstile iframe
            turnstile = await page.query_selector("iframe[src*='challenges.cloudflare.com']")
            if turnstile:
                print("  [!] Turnstile Iframe DETECTED")
                # Check if it's failed or waiting
                is_visible = await turnstile.is_visible()
                print(f"  [!] Is Visible: {is_visible}")
            else:
                print("  [+] No Turnstile Iframe found (might have passed or not loaded)")
                
            await page.screenshot(path="diag_result.png")
            print("\nScreenshot saved as diag_result.png")
            
        except Exception as e:
            print(f" Error: {e}")
        finally:
            proc.terminate()

if __name__ == "__main__":
    asyncio.run(run_diag())
