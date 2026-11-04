"""Author and freeze challenge splits BEFORE running predictions.

Hand-authored, synthetic, not independent human annotation. Separate scenario
families across validation and test. No production decisions inspect these texts.
"""
import hashlib,json
from pathlib import Path

def rows(split, groups):
    result=[]
    for kind,label,texts in groups:
        for text in texts:
            result.append({'id':f'{split}-{len(result)+1:03}','kind':kind,'text':text,
                'acceptable_labels':label.split('|') if label else [],'must_review':kind!='paraphrase'})
    return result

validation=[
('paraphrase','PAYMENT',['My debit card gets rejected at checkout.','A transaction appears twice on my statement.','Which ways of paying do you accept?']),
('paraphrase','REFUND',['How long until my reimbursement reaches me?','What conditions apply to getting my money back?','Please return the money for the unwanted item.']),
('paraphrase','ACCOUNT',['I forgot the secret phrase for signing in.','I want to close my customer profile permanently.','Can I register a new customer login?']),
('paraphrase','ORDER',['I want to purchase a replacement kettle.','Stop the purchase I submitted this morning.','How far along is my purchase?']),
('paraphrase','SHIPPING',['The destination on my purchase needs correcting.','Save my new postal address for future purchases.','Send the package to my office instead.']),
('paraphrase','DELIVERY',['Is express delivery available?','How many days does delivery normally take?','Do you offer weekend delivery?']),
('paraphrase','INVOICE',['Email me the bill for my last purchase.','The invoice contains an incorrect amount.','Where can I download my receipt?']),
('paraphrase','CONTACT',['Connect me with a support representative.','What number can I call for customer assistance?','How do I speak with a real person?']),
('paraphrase','FEEDBACK',['I would like to share a suggestion about your store.','Your service was terrible and I want to complain.','Where can I leave a product review?']),
('paraphrase','CANCEL',['Will I be charged a penalty if I cancel?','What is the cancellation charge?','Does withdrawing a purchase incur a fee?']),
('paraphrase','SUBSCRIPTION',['Stop sending your promotional newsletter.','Sign me up for your email newsletter.','How can I opt out of marketing emails?']),
('vague','',['Can somebody look into this?','It did not work as I expected.','I have a problem with your service.','Help me sort this out.','This is really confusing.','I need assistance urgently.','There is an issue here.','I am unhappy about what happened.','Can you fix it for me?','Things are not going well.']),
('mixed','PAYMENT|REFUND',['My card was billed incorrectly and I want a reimbursement.','There is a second debit and I need the extra funds returned.']),
('mixed','ACCOUNT|ORDER',['Delete my profile and cancel the purchase.','Reset my password and tell me where my purchase is.']),
('mixed','SHIPPING|INVOICE',['Change my destination and send me a receipt.','Correct my postal address and fix the invoice.']),
('mixed','REFUND|CONTACT',['Where is my reimbursement and how do I speak to an agent?','Send my money back and connect me with support.']),
('mixed','SUBSCRIPTION|DELIVERY',['Remove me from the mailing list and explain express delivery.','Subscribe me to promotions and explain delivery times.']),
('out_of_scope','',['Write me a Python program.','What is the weather in Madrid?','Recommend a pasta recipe.','My dog refuses to eat.','Translate this poem into French.','Solve a quadratic equation.','Tell me about the Roman empire.','Book a medical appointment.','Can you diagnose a headache?','Who won the football game?','My computer has a blue screen.','I need advice on a mortgage.'])]
heldout=[
('paraphrase','PAYMENT',['The checkout refuses my bank card even though it has funds.','One item cost me two separate debits; please investigate the billing.','Can I settle the bill using a digital wallet?','The funds were deducted but checkout said the transaction failed.','I tapped pay once but my bank lists the purchase in duplicate.','A single shopping trip has taken two bites out of my balance.']),
('paraphrase','REFUND',['The returned shoes were accepted; where is the promised credit?','Am I eligible to get my money back after opening the box?','I sent the item back and want the purchase price repaid.','What is the deadline for requesting reimbursement?','The refund was approved last week but still has not arrived.','Please reimburse the cost of this defective lamp.']),
('paraphrase','ACCOUNT',['The password recovery link never reaches my inbox.','Erase my customer registration and its stored profile.','I cannot finish creating a login because registration fails.','I need to change the name on my profile.']),
('paraphrase','ORDER',['Remove the blender from my existing purchase.','Has the parcel from purchase number 7841 been dispatched?','Please abandon the purchase before it is processed.','I would like to buy three notebooks from your shop.']),
('paraphrase','SHIPPING',['The parcel should go to apartment 8 rather than apartment 3.','My next purchases should use the new house address.','I entered the old postcode; please redirect the package.','How do I store a default destination for parcels?']),
('paraphrase','DELIVERY',['Can you ship using an overnight courier service?','What is your standard transit time to rural areas?','Are there several courier speeds to choose from?','Will delivery typically take more than a week?']),
('paraphrase','INVOICE',['Please issue a tax invoice for the headphones.','The VAT total printed on my bill looks incorrect.','I need another copy of the purchase invoice for accounting.','How do I inspect the itemized bill for my purchase?']),
('paraphrase','CONTACT',['Please transfer this conversation to a human employee.','Where is the telephone helpline for shoppers?','Can a member of your customer service staff talk to me?','I need the support departments contact details.']),
('paraphrase','FEEDBACK',['I want to report how rudely I was treated by your staff.','Your packaging was excellent and I would like to leave a rating.','Here is a suggestion to improve the shopping experience.','Where should I post my opinion about this product?']),
('paraphrase','CANCEL',['Is there a financial penalty for withdrawing this purchase?','Before stopping my purchase I want to know the cancellation cost.','Do you deduct any money for a cancellation?','How much will cancelling the reservation cost me?']),
('paraphrase','SUBSCRIPTION',['Please take my email off the promotional mailing list.','I want your weekly newsletter to arrive in my inbox.','The marketing bulletin should no longer be sent to me.','Where is the signup for your shop newsletter?']),
('vague','',['This situation needs attention.','I cannot figure out what to do next.','Please investigate what happened yesterday.','Your system is giving me trouble.','I need somebody to sort everything out.','There seems to be a mistake somewhere.','I am stuck again.','This has gone badly and I need a response.','What should I do about this?','It happened a second time.','Can you explain why this is happening?','Nothing seems right today.']),
('mixed','PAYMENT|ACCOUNT',['My balance was debited twice and I also need my password reset.','Fix the rejected card transaction and delete my customer profile.']),
('mixed','PAYMENT|REFUND',['The shop took an extra debit; reverse it and investigate the payment failure.','I need to dispute the duplicate card charge and track an earlier refund.']),
('mixed','ORDER|SUBSCRIPTION',['Cancel the kettle purchase and stop the promotional bulletin.','Tell me where my parcel is and sign me up for store news.']),
('mixed','SHIPPING|DELIVERY',['Redirect my parcel to the hotel and tell me how long delivery takes.','Save the new address and explain your overnight courier choices.']),
('mixed','INVOICE|ACCOUNT',['Correct the tax invoice and help me regain access to my login.','Send the itemized bill and change my customer profile name.']),
('mixed','REFUND|FEEDBACK',['Check my reimbursement status and record a complaint about the staff.','Explain the refund deadline and show me where to leave a rating.']),
('out_of_scope','',['Generate a logo for my bakery.','How do I repair a leaking tap?','Explain quantum entanglement simply.','My bicycle gears keep slipping.','Find me a flight to Tokyo.','Give me a workout plan.','Can you summarize a novel?','What is the population of Iceland?','I need help with my algebra homework.','Tell me a bedtime story.','My refrigerator is making a loud noise.','Suggest names for a new puppy.','Which insurance policy should I choose?','How do I renew my passport?','Is this mushroom safe to eat?','Can you compose a birthday song?'])]
root=Path('data/challenge')
for split,groups in [('validation',validation),('test',heldout)]:
    path=root/f'{split}.jsonl'
    if path.exists():raise SystemExit('Refusing to overwrite frozen challenge data')
    path.write_text(''.join(json.dumps(r)+'\n' for r in rows(split,groups)),encoding='utf-8')
manifest={'purpose':'Small author-created behavioral challenge, not production accuracy or independently annotated evaluation.',
 'label_policy':'Single supported intent => listed category. Vague, unrelated, or multiple actionable intents => must review, even if one category is plausible. PAYMENT is billing/payment issues; REFUND is repayment request/policy/status. Returns is invented team name, not dataset label.',
 'development_cases_excluded':['Money left my account two times for one purchase.','Something is wrong. Please help.','I was charged twice for the same order. Can you refund the extra payment?'],
 'splits':{s:{'sha256':hashlib.sha256((root/f'{s}.jsonl').read_bytes()).hexdigest(),'count':len((root/f'{s}.jsonl').read_text().splitlines())} for s in ['validation','test']},
 'protocol':'Freeze both sets before scoring. Fit classifier on existing Bitext train only; calibrate on part of original validation; select routing gates/model using remaining validation and challenge validation only. Score challenge test only after policy/model selection artifacts are frozen. Do not tune further after test.'}
(root/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps(manifest,indent=2))
