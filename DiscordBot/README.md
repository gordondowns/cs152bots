Current functionality:
- Auto-flag message if any toxicity level according to perspective > 0.9. This includes sending an innocuous message and editing it to something bad. The bot will react to the message with 🤬
- Mock the user flow. After the user completes the flow, generate a report and immediately forward it to mod channel (can be later changed to on-command forwarding based on condition at location). The bot will react to the message with 🛑
- Stop a user from submitting multiple reports on the same message  (can add more conditions later)

updated functionality:
- only send auto-flagged message to moderator for unconfident predictions (all toxicity levels are between 0.5 and 0.9)
- The moderator type "review the next report in the queue" in the mod channel to start reviewing the next report in the priority queue
  (currently priority is given by the reporting time )
  

Extra packages to install:
- `unidecode`
  
TODO:
- change priority of the review queue
- TODO: delete "filter out similar" form user flow code