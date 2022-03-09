import json
import re

original_dict = {'reported_content': "Congratulations bitcoin giveaway\nClick here!", 'reported_account': 211650790534676481, 'report_time': '2022-03-08 20:37:15.520599', 'reporter_account': None, 'mod_report': {'message': {'author_id': 211650790534676481, 'author': 'gordizzle', 'content': "Congratulations bitcoin giveaway\nClick here!", 'url': 'https://discord.com/channels/915746011757019217/930035531889401866/950975524610641971'}}, 'scores': {'PROFANITY': 0.025118273, 'SEVERE_TOXICITY': 0.014484765, 'THREAT': 0.067497976, 'IDENTITY_ATTACK': 0.02359231, 'TOXICITY': 0.036912862, 'CRYPTO_SCAM': 0.6521553949768816}, 'auto_flagged': True, 'reported_account_abusive_strike': 0}

# original_dict = {
#   "reported_content": "Go here -> https://newcryptoscam.com/",
#   "reported_account": 211650790534676481,
#   "report_time": "2022-03-08 20:48:51.380237",
#   "reporter_account": 211650790534676481,
#   "mod_report": {
#     "report_dm_channel_id": 946605839865757748,
#     "reporter": "gordizzle",
#     "immediate_danger": False,
#     "timestamp": "2022-03-08 20:48:51.380237",
#     "message": {
#       "author_id": 211650790534676481,
#       "author": "gordizzle",
#       "content": "Go here -> https://newcryptoscam.com/",
#       "url": "https://discord.com/channels/915746011757019217/930035531889401866/950952759342039060"
#     },
#     "Category": "Fraud / Scam",
#     "crypto_scam": True,
#     "Sub-category": "Cryptocurrency Scam",
#     "justification": [
#       "this is a scam"
#     ],
#     "account_status": "Reported not compromised."
#   },
#   "scores": "null",
#   "auto_flagged": False,
#   "reported_account_abusive_strike": 0,
#   "reporter_account_malicious_strike": 0
# }

print(original_dict)


modified_dict = {k:v for k,v in original_dict.items() if v != None}


out = json.dumps(modified_dict, indent=4)

print(out)

out2 = out.replace('{','').replace('}','').replace('[','').replace(']','').replace(',','').replace('"','').replace('\\n','  ')

# replace blank lines with nothing
out2 = "\n".join([line for line in out2.split('\n') if line.strip() != ""])


print(out2)