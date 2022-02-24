from enum import Enum, auto
import datetime;
import discord
import json
import re

IMM_DANGER_RESPONSE = "Thank you for the information. Our content moderation team will review the message and notify the local authorities if necessary. Please contact 911 for immediate support."
NORMAL_REPORT_RESPONSE = "Thank you for the information. Our content moderation team will review the message and reach out if needed. No further action is required on your part."

class State(Enum):
    REPORT_START = auto()
    AWAITING_MESSAGE_URL = auto()
    MESSAGE_IDENTIFIED = auto()
    CATEGORIZE_MESSAGE = auto()
    REPORT_SUBMITTED = auto()
    REPORT_CANCELLED = auto()

class Categories(Enum):
    COMP_ACCOUNT = "This account may be compromised"
    HARASSMENT = "Harassment / Offensive Content"
    IMM_DANGER = "Immediate Danger"
    SCAM = "Fraud / Scam"

class Report:
    START_KEYWORDS = {"r", "report"}
    CANCEL_KEYWORDS = {"c", "cancel"}
    HELP_KEYWORDS = {"h", "help"}
    STATE_KEYWORD = {"s"} # DEBUG: get state

    def __init__(self, client):
        self.state = State.REPORT_START
        self.client = client
        self.message = None
        self.dm_channel = None
        self.timestamp = None
        self.message_url = ""
        self.reporter_id = None
        self.mod_report = {}
    
    async def handle_message(self, message):
        '''
        This function makes up the meat of the user-side reporting flow. It defines how we transition between states and what 
        prompts to offer at each of those states. You're welcome to change anything you want; this skeleton is just here to
        get you started and give you a model for working with Discord. 
        '''

        if message.content.lower in self.STATE_KEYWORD:
            return ["My state is " + str(self.state.name)]

        if message.content.lower() in self.CANCEL_KEYWORDS:
            return self.report_cancelled()
        
        if self.state == State.REPORT_START:
            return self.report_start()
        
        if self.state == State.AWAITING_MESSAGE_URL:
            await self.awaiting_message_url(message)

        return []

    def report_cancelled(self):
        self.state = State.REPORT_CANCELLED
        return ["Report cancelled. Have a nice day!"]

    def report_start(self):
        reply =  "Thank you for starting the reporting process. "
        reply += "Say `help` at any time for more information.\n\n"
        reply += "Please copy paste the link to the message you want to report.\n"
        reply += "You can obtain this link by right-clicking the message and clicking `Copy Message Link`."
        self.state = State.AWAITING_MESSAGE_URL
        return [reply]

    async def awaiting_message_url(self, message):
        # DEBUG: use known Link
        if message.content.lower() == "test": 
            m = re.search('/(\d+)/(\d+)/(\d+)', "https://discord.com/channels/915746011757019217/930035531889401866/944172931141992468")

        else:
            # Parse out the three ID strings from the message link
            m = re.search('/(\d+)/(\d+)/(\d+)', message.content)
        
        if not m:
            return ["I'm sorry, I couldn't read that link. Please try again or say `cancel` to cancel."]

        guild = self.client.get_guild(int(m.group(1)))
        if not guild:
            return ["I cannot accept reports of messages from guilds that I'm not in. Please have the guild owner add me to the guild and try again."]
        
        channel = guild.get_channel(int(m.group(2)))
        if not channel:
            return ["It seems this channel was deleted or never existed. Please try again or say `cancel` to cancel."]
        
        try:
            # note that message is the user dm and self.message is the reported message!
            self.message = await channel.fetch_message(int(m.group(3)))
            self.message_url = message.content
            self.dm_channel = message.channel
            self.reporter_id = message.author.id
            self.state = State.MESSAGE_IDENTIFIED
        except discord.errors.NotFound:
            return ["It seems this message was deleted or never existed. Please try again or say `cancel` to cancel."]

        # Here we've found the message
        if self.client.check_message_url_against_active_reports(message.author.id, message.content):
            self.state = State.REPORT_CANCELLED
            await self.dm_channel.send("Report cancelled: you have already submitted a report on this message.")
            return []

        await self.dm_channel.send(f"I found this message:\n```{self.message.author.name}: {self.message.content}```\n")

        self.mod_report["report_dm_channel_id"] = message.channel.id
        self.mod_report["reporter"] = message.author.name
        self.timestamp = datetime.datetime.now()
        self.mod_report["timestamp"] = str(self.timestamp)
        self.mod_report["message"] = {
            "author_id": self.message.author.id,
            "author": self.message.author.name, 
            "content": self.message.content,
            "url": self.message_url
        }

        await self.categorize_message()
        
    async def categorize_message(self):
        self.state = State.CATEGORIZE_MESSAGE
        await self.dm_channel.send("Please tell us a bit more about this message.")

        choices = [e.value for e in Categories]
        user_choice = await self.prompt_for_choice(choices)
        self.mod_report["Category"] = choices[user_choice]
        self.mod_report["crypto_scam"] = False

        if Categories(choices[user_choice]) == Categories.COMP_ACCOUNT:
            self.mod_report["account_status"] = "Reported to be compromised."
            await self.more_info()
            await self.block_user()

        elif Categories(choices[user_choice]) == Categories.HARASSMENT:
            sub_choices = ["Hate speech", "Cyberbulling", "Sexual Content", "Illegal Activity", "Fake News", "Other / I don't like this post"]
            user_choice = await self.prompt_for_choice(sub_choices)
            self.mod_report["Sub-category"] = sub_choices[user_choice]
            
            await self.more_info()
            await self.compromised_acct()
            await self.block_user()

        elif Categories(choices[user_choice]) == Categories.IMM_DANGER:
            await self.send_report(IMM_DANGER_RESPONSE)
            return
        
        elif Categories(choices[user_choice]) == Categories.SCAM:
            sub_choices = ["Cryptocurrency Scam", "Financial Scam", "Phishing", "Impersonation", "Other"]
            user_choice = await self.prompt_for_choice(sub_choices)
            self.mod_report["Sub-category"] = sub_choices[user_choice]

            if sub_choices[user_choice] == "Cryptocurrency Scam":
                self.mod_report["crypto_scam"] = True
                await self.crypto_specific()

            await self.more_info()
            await self.compromised_acct()
            await self.block_user()

        await self.send_report(NORMAL_REPORT_RESPONSE)

    async def prompt_for_choice(self, choices):
        reply = f"\n\nPlease enter a number between 1 and {len(choices)}:\n"
        for i, choice in enumerate(choices):
            reply += f"{i+1}) {choice}\n"
        await self.dm_channel.send(reply)

        def check(msg):
            return msg.content.isnumeric() and 0 < int(msg.content) and int(msg.content) <= len(choices)

        msg = await self.client.wait_for("message", check=check)
        return int(msg.content)-1

    async def crypto_specific(self):
        # #TODO: modify this part according to the updated user flow?
        # await self.dm_channel.send("Would you like us to automatically filter out messages similar to this one for the next 24 hours? This change will only be visible to you. Enter 'y' or 'n'.")
        #
        # def check(msg):
        #     return msg.content.lower() in {'y', 'n'}
        #
        # msg = await self.client.wait_for("message", check=check)
        # if msg.content.lower() == 'y':
        #     await self.dm_channel.send(f"MOCKED: Similar messages are filtered!")
        return

    async def more_info(self):
        await self.dm_channel.send("Would you like to provide more information? \nEnter 'skip' to skip this step, and 'done' when finished.")
        msg = await self.client.wait_for("message")
        self.mod_report["justification"] = []

        if msg.content.lower() != "skip":
            while msg.content.lower() != "done":
                self.mod_report["justification"].append(msg.content)
                msg = await self.client.wait_for("message")
        
    async def block_user(self):
        await self.dm_channel.send("Would you like to block this user? Enter 'y' or 'n'.")

        def check(msg):
            return msg.content.lower() in {'y', 'n'}

        msg = await self.client.wait_for("message", check=check)
        if msg.content.lower() == 'y':
            await self.dm_channel.send(f"MOCKED: {self.message.author.name} is blocked!")
            self.mod_report["user_action"] = f"Reporter blocked {self.message.author.name}."

    async def compromised_acct(self):
        await self.dm_channel.send("Do you think this account has been compromised? Enter 'y', 'n', or 'u' for 'unsure'.")

        def check(msg):
            return msg.content.lower() in {'y', 'n', 'u'}

        msg = await self.client.wait_for("message", check=check)
        if msg.content.lower() == 'y':
            self.mod_report["account_status"] = "Reported to be compromised."
        elif msg.content.lower() == 'u':
            self.mod_report["account_status"] = "Reported may be compromised."
        else:
            self.mod_report["account_status"] = "Reported not compromised."


    async def send_report(self, success_message):
        # ask bot to forward the message to the mod channel
        sent, reason = self.client.handle_user_report_submission(self.reporter_id, self.mod_report)
        if sent: 
            await self.message.add_reaction("🇶") # means the message is reported
            await self.dm_channel.send(success_message)
            self.state = State.REPORT_SUBMITTED
        else: 
            await self.dm_channel.send(f"Your report is cancelled due to the following reason:\n{reason}")
            self.state = State.REPORT_CANCELLED

    def report_complete(self):
        return self.state == State.REPORT_SUBMITTED or self.state == State.REPORT_CANCELLED

    def report_submitted(self):
        return self.state == State.REPORT_SUBMITTED

    def get_timestamp(self):
        return self.timestamp

    def get_message_url(self):
        return self.message_url
    


    

