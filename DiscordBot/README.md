Current functionality:
- Mock the user flow. After the user completes the flow, generate a report and add it to a queue. The bot will react to the message with 🛑
- Stop a user from submitting multiple reports on the same message  (can add more conditions later)

Updated functionality for user flow:
- delete "filter out similar" from user flow code as we discussed? 
- Auto-flag message if any toxicity level (perspective/customized) > 0.9 This includes sending an innocuous message and editing it to something bad. 
  The bot will react to the message with 🤬
- only send auto-flagged message to moderator for unconfident predictions (all toxicity levels are between 0.5 and 0.9). react to this message with ❓
- The bot maintains a queue of reports to be reviewed (user report/automatically flagged with low confidence):
  Note: currently priority is given by the reporting time: can be tested by first message "money", 
  then message "send money to me", then let the user report "money" to the bot. ("send money to me" should be processed first).

Manual flow
- The moderator type in the mode channel "review the next report in the queue" in the mod channel to start reviewing the next report in the priority queue
- Check for Malicious user report: remove 🛑
  1) warning 
  2) warning +suspended for the reporter account
  (bot DM warning to the reporter in the reporting channel; 
   if suspend then if the reporter send another report within 1 minute, 
     that report would fail; report feature recovers after 1 minute)
- Check for Immediate danger:remove 🛑 for user report, remove ❓For auto-flagged message
  1) yes:change the message reaction to "🆘"
  2) no
- Check for Escalate to higher level:remove 🛑 for user report, remove ❓For auto-flagged message
  1) yes: change the message reaction to "👨‍💼"
  2) no
- Check for Include scam url: (yes,add url/no)
- Pick reported content outcome: remove 🛑 for user report, remove ❓For auto-flagged message
  1) no action
  2) flag: flag the message with ‼
- Pick reported account outcome: 
  1) no action
  2) temp deactivate 1 day: bot dms the scammer account about deactivation
  3) temp deactivate 7 days: bot dms the scammer account about deactivation
  4) permanently deactivate: bot dm the scammer account about deactivation


  

Extra packages to install:
- `unidecode`
  
TODO:
- check whether it matches the updated user flow