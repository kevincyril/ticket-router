"""Run against a built dashboard, real API, dispatcher, and process worker."""
import os
from pathlib import Path
import pytest


@pytest.mark.browser

def test_browser_flow():
    if not os.getenv('BROWSER_BASE_URL'):
        pytest.skip('Set BROWSER_BASE_URL after launching the full stack')
    from playwright.sync_api import sync_playwright, expect
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page(viewport={'width':1440,'height':1000})
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(os.environ['BROWSER_BASE_URL'])
        expect(page.get_by_text('Review-first mode: every new ticket',exact=False)).to_be_visible()
        page.get_by_role('button',name='New ticket',exact=True).click()
        text='I was charged twice for the same purchase. Can you help? Demo reference '+__import__('uuid').uuid4().hex[:8]+'.'
        page.get_by_label('Support request',exact=True).fill(text)
        page.get_by_role('button',name='Submit ticket',exact=True).click()
        expect(page.get_by_role('status')).to_contain_text('Ticket received')
        row=page.locator('tbody tr').filter(has_text=text)
        expect(row).to_be_visible(timeout=15000)
        expect(row.locator('.status')).to_have_text(__import__('re').compile('Routed|Needs review'),timeout=120000)
        row.click()
        expect(page.get_by_role('dialog')).to_be_visible()
        expect(page.get_by_role('dialog')).to_contain_text('Automatic Routing Disabled')
        if page.get_by_role('button',name='Save routing decision').count():
            page.get_by_label('Correct category').select_option('PAYMENT')
            page.get_by_role('button',name='Save routing decision').click()
            expect(page.get_by_role('dialog')).to_contain_text('Reviewed by')
        page.get_by_role('button',name='Close details').click()
        page.get_by_role('button',name='Model evaluation',exact=True).click()
        expect(page.get_by_role('heading',name='Realistic wording exposes the gap.')).to_be_visible()
        expect(page.get_by_text('TEST MACRO-F1').first).to_be_visible()
        assert not errors,errors
        Path('test-results').mkdir(exist_ok=True)
        page.screenshot(path='test-results/evaluation.png',full_page=True)
        page.get_by_role('button',name=__import__('re').compile('Ticket inbox')).click()
        page.screenshot(path='test-results/dashboard.png',full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        page.screenshot(path='test-results/mobile.png',full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        browser.close()
