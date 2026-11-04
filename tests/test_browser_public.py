import os
import uuid
import pytest


@pytest.mark.browser
def test_public_custom_request_can_be_typed_edited_and_submitted():
    base=os.environ.get('PUBLIC_BROWSER_BASE_URL')
    if not base:pytest.skip('Set PUBLIC_BROWSER_BASE_URL to the hosted demo')
    from playwright.sync_api import sync_playwright,expect
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page(viewport={'width':1440,'height':1000})
        page_errors=[]
        page.on('pageerror',lambda error:page_errors.append(str(error)))
        page.goto(base,timeout=120000)
        expect(page.get_by_text('Shared public sandbox:',exact=False)).to_be_visible()
        page.get_by_role('button',name='New ticket',exact=True).click()
        field=page.get_by_label('Support request',exact=True)
        expect(field).to_be_editable()
        # Replace prefilled text using real keyboard events, not programmatic fill.
        page.get_by_role('button',name='Duplicate charge',exact=False).click()
        field.press('ControlOrMeta+A')
        initial='I was billed twice for a book. Demo '+uuid.uuid4().hex[:8]
        field.press_sequentially(initial)
        expect(field).to_have_value(initial)
        # Replace the draft, then use Enter inside the modal to add another line.
        edited=initial.replace('a book','one notebook')
        field.press('ControlOrMeta+A')
        field.press_sequentially(edited)
        field.press('Enter')
        field.press_sequentially('Please investigate the duplicate debit.')
        edited+='\nPlease investigate the duplicate debit.'
        # A real periodic refresh must not overwrite the controlled draft.
        with page.expect_response(lambda r:r.url.endswith('/api/model') and r.request.method=='GET',timeout=15000):
            pass
        expect(field).to_have_value(edited)
        expect(field).to_be_editable()
        with page.expect_response(lambda r:r.url.endswith('/api/tickets') and r.request.method=='POST') as posted:
            page.get_by_role('button',name='Submit ticket',exact=True).click()
        response=posted.value
        assert response.status==202
        assert response.request.post_data_json=={'text':edited}
        ticket=response.json()
        assert ticket['text']==edited
        expect(page.get_by_role('dialog')).not_to_be_visible()
        persisted=page.request.get(base.rstrip('/')+'/api/tickets/'+ticket['id'])
        assert persisted.status==200 and persisted.json()['text']==edited
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
        assert not page_errors,page_errors
        page.screenshot(path='test-results/public-custom-request.png',full_page=True)
        browser.close()
