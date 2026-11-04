import os
import pytest


@pytest.mark.browser
def test_public_synthetic_demo_browser():
    base=os.environ.get('PUBLIC_BROWSER_BASE_URL')
    if not base:pytest.skip('Set PUBLIC_BROWSER_BASE_URL to the hosted demo')
    from playwright.sync_api import sync_playwright,expect
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page(viewport={'width':1440,'height':1000})
        page.goto(base)
        expect(page.get_by_text('Shared public sandbox:',exact=False)).to_be_visible()
        page.get_by_role('button',name='New ticket',exact=True).click()
        expect(page.get_by_label('Support request',exact=True)).not_to_be_editable()
        page.get_by_role('button',name='Duplicate charge',exact=False).click()
        with page.expect_response(lambda r:r.url.endswith('/api/tickets') and r.request.method=='POST') as posted:
            page.get_by_role('button',name='Submit ticket',exact=True).click()
        response=posted.value
        assert response.status==202
        ticket=response.json()
        row=page.locator('tbody tr').filter(has_text=ticket['id'][:8].upper())
        expect(row.locator('.status')).to_have_text('Needs review',timeout=90000)
        row.click()
        expect(page.get_by_role('dialog')).to_be_visible()
        expect(page.get_by_label('Review note (optional)')).to_be_disabled()
        expect(page.get_by_label('Reviewer',exact=True)).not_to_be_editable()
        page.get_by_label('Correct category').select_option('PAYMENT')
        page.get_by_role('button',name='Save routing decision').click()
        expect(page.get_by_role('dialog')).to_contain_text('Reviewed by Demo visitor')
        page.get_by_role('button',name='Close details').click()
        page.get_by_role('button',name='Model evaluation',exact=True).click()
        expect(page.get_by_role('heading',name='Realistic wording exposes the gap.')).to_be_visible()
        page.screenshot(path='test-results/public-demo.png',full_page=True)
        browser.close()
