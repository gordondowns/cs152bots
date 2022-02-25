Auto flagging
- Currently has three main ways of being auto-flagged: 1. From the Perspective API, 2. From our crypto scam Naive Bayes classifier, 3. From our internal blacklist of known scam URLs/Bitcoin addresses
- Perspective API and crypto scam classifier: Auto-flag message if any toxicity level (perspective/customized) > 0.9. This includes sending an innocuous message and editing it to something bad. The bot will react to the message with 🤬. Only send auto-flagged message to moderator for unconfident predictions (toxicity level between 0.5 and 0.9), and will react to this message with ❓
- Blacklist: For URLs, the regex will identify addresses that start with "https://" or "http://" and check those against the blacklist. For Bitcoin addresses, the regex will identify addresses in the P2PKH, P2SH, or Bech32 formats (e.g., 15a8R7dAVBnXxYkAkL4Rp7HeY3jacb2N3B, 37QgMqfZpzCqA9mMfokWGy5pNh7g1xFfPi, and bc1qxch7fme8karau7rl3s7pt2mfj2y6n8nzpj2d6u, respectively).

User flow
- DM the bot "report" to start a user report.
- Mock the user flow. After the user completes the flow, generate a report and add it to a queue. The bot will react to the message with 🇶 (since this sounds like "queue").
- Prevents a user from submitting multiple reports on the same message
- Can type "help" during the report to see additional commands

Manual flow
- The bot maintains a queue of reports to be reviewed (user report/automatically flagged with low confidence):
  Note: currently priority is given first to user reports marked as "Immediate Danger," then by reporting time. Can test the reporting time by first messaging "money", then "send money to me", then let the user report "money" to the bot. ("send money to me" should be processed first).
- In the mod channel, type "next report" to start reviewing the next report in the priority queue
- Check if it is a malicious/frivolous user report: also remove 🇶 emoji. Note that this option only appears for user reports, not auto-flagging. If yes, the options are:
  1) Give user a warning 
  2) Give user a warning + suspend the reporting account (bot sends a DM warning to the reporter; if suspended then if the reporter sends another report within 1 minute, that report will fail; report feature recovers after 1 minute)
- Check for Immediate danger: remove 🇶 for user report, remove ❓ for auto-flagged message. Options:
  1) yes: change the message reaction to "🆘"
  2) no
- Check for Escalate to higher level: remove 🇶 for user report, remove ❓ for auto-flagged message. Options:
  1) yes: change the message reaction to "👨‍💼"
  2) no
- Check for Include scam url: Options:
  1. Yes, add it (then reviewer can add it to the blacklist)
  2. No
- Choose reported content outcome: remove 🇶 for user report, remove ❓ for auto-flagged message
  1) no action
  2) flag: flag the message with ‼
- Choose reported account outcome:
  1) no action
  2) temp deactivate 1 day: bot DMs the scammer account about deactivation
  3) temp deactivate 7 days: bot DMs the scammer account about deactivation
  4) permanently deactivate: bot DMs the scammer account about deactivation


  

Extra packages to install:
- `unidecode`
- `scikit-learn`
  
TODO:
- check whether it matches the updated user flow