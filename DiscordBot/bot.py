# bot.py
import discord
from discord.ext import commands
import os
import json
import logging
import re
import requests
from collections import defaultdict
from report import Report
from unidecode import unidecode
from queue import PriorityQueue
from dataclasses import dataclass, field
import datetime
from enum import Enum, auto
import pickle
import copy
from crypto_scam_classifier import naive_bayes_classifier

# Thresholds
PROFANITY_THRESHOLD = 0.65 #the threshold of being suspicious
PROFANITY_THRESHOLD_Moderation = 0.9 #manual review if PROFANITY_THRESHOLD< score < PROFANITY_THRESHOLD_Moderation
MALICIOUS_REPORTER_SUSPEND_TIME = 1 #in mins
SCAMMER_DEACT_TIME_SHORT = 1 #in days
SCAMMER_DEACT_TIME_LONG = 7 #in days

# Set up logging to the console
logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

# There should be a file called 'token.json' inside the same folder as this file
token_path = 'tokens.json'
if not os.path.isfile(token_path):
    raise Exception(f"{token_path} not found!")
with open(token_path) as f:
    # If you get an error here, it means your token is formatted incorrectly. Did you put it in quotes?
    tokens = json.load(f)
    discord_token = tokens['discord']
    perspective_key = tokens['perspective']

# Load classifier and vectorizer that were trained on our Discord dataset
vectorizer = pickle.load(open("crypto_scam_classifier/vectorizer_disc.pickle", "rb"))
classifier = pickle.load(open("crypto_scam_classifier/model_disc.pickle", "rb"))

@dataclass(order=True)
class PrioritizedReport:
    priority: (int, datetime)
    item: object = field()

class ForwardedReport(object):
    reported_content = None #reported message content
    reported_account = None
    reporter_account = None #for user report
    mod_report = None #manual report for user report
    scores = None  # heuristics for auto report
    timestamp = None
    auto_flagged = False

    def __init__(self, reported_content, reported_account, timestamp, reporter_account=None,
                 mod_report = None, scores = None, auto_flagged = False):
        self.reported_content = reported_content
        self.reported_account = reported_account
        self.reporter_account = reporter_account
        self.mod_report = mod_report
        self.scores = scores
        self.auto_flagged = auto_flagged
        self.report_time = timestamp

    def fmtodict(self, abusive_reported_acc_strike, malicious_reporter_strike):
        fmdict = {}
        fmdict["reported_content"] = self.reported_content
        fmdict["reported_account"] = self.reported_account
        fmdict["report_time"] = self.report_time

        fmdict["reporter_account"] = self.reporter_account
        fmdict["mod_report"] = self.mod_report
        fmdict["scores"] = self.scores
        fmdict["auto_flagged"] = self.auto_flagged

        reported_strike = 0
        if self.reported_account in abusive_reported_acc_strike:
            reported_strike = abusive_reported_acc_strike[self.reported_account]
        fmdict["reported_account_abusive_strike"] = reported_strike

        if self.reporter_account is not None:
            reporter_strike = 0
            if self.reporter_account in malicious_reporter_strike:
                reporter_strike = malicious_reporter_strike[self.reporter_account]
            fmdict["reporter_account_malicious_strike"] = reporter_strike
        return fmdict



def dicttofm(fmdict):
    return ForwardedReport(fmdict["reported_content"], fmdict["reported_account"], fmdict["report_time"],
                           fmdict["reporter_account"], fmdict["mod_report"], fmdict["scores"], fmdict["auto_flagged"])




class ActiveReport(object):
    author = None
    report = None
    timestamp = None
    message_url = None

    def __init__(self, author, report, timestamp, message_url):
        self.author = author
        self.report = report
        self.timestamp = timestamp
        self.message_url = message_url

class ModBot(discord.Client):
    def __init__(self, key):
        intents = discord.Intents.default()
        super().__init__(command_prefix='.', intents=intents)
        self.group_num = 16
        self.mod_channel = {} # Map from guild to the mod channel id for that guild
        self.reports = {} # Map from user IDs to the state of their report


        # Map from user IDs to their active report(s) that has not been moderated
        def user_reports_stats():
            return {
                "timestamps": [],
                "message_urls": []
            } 
        self.user_active_reports = defaultdict(user_reports_stats)
        self.all_active_reports = []
        self.perspective_key = key
        self.review_queue = PriorityQueue()
        self.malicious_reporter_ids = {} #map malicious user id to the time their report feature is suspeneded
        self.scamaddr = set(['15a8R7dAVBnXxYkAkL4Rp7HeY3jacb2N3B', #platform's internal blacklist of scam URLs/crypto addresses. Initializing with a few examples
                             'bc1qxch7fme8karau7rl3s7pt2mfj2y6n8nzpj2d6u',
                             '37QgMqfZpzCqA9mMfokWGy5pNh7g1xFfPi',
                             'thisisacryptoscam.com',
                             'giveawayscams.com'])


        self.moderator_state = "Free" #"Free" if the moderator is done with a report, #"Busy" if dealing with a report, check before send msg to mod_channel
        self.abusive_reported_acc_strike = {}
        self.malicious_reporter_strike = {}

    async def check_review_queue(self):
        nextmsg = None
        if not self.review_queue.empty():
            nextmsg = self.review_queue.get().item
            d = copy.deepcopy(nextmsg.fmtodict(self.abusive_reported_acc_strike, self.malicious_reporter_strike))

            # get rid of duplicated and/or unnecessary fields
            d.pop('reported_content',None)
            d.pop('reported_account',None)
            d.pop('reporter_account',None)
            d['mod_report'].pop('report_dm_channel_id',None)
            d['mod_report'].pop('timestamp',None)
            d['mod_report']['message'].pop('author_id',None)
            d['mod_report']['message'].pop('url',None)
            d['mod_report']['message']['content'] = unidecode(d['mod_report']['message']['content'])
            if d['scores'] != None:
                d['scores'] = {k:round(v,3) for k,v in d['scores'].items()}
            # get rid of null values
            d = {k:v for k,v in d.items() if v != None}
            report_str = json.dumps(d, indent=4)
            # replace JSON formatting characters
            report_str = report_str.replace('{','').replace('}','').replace('[','').replace(']','') \
                .replace(',','').replace('"','').replace('\\n','  ')
            # get rid of blank lines
            report_str = "\n".join([line for line in report_str.split('\n') if line.strip() != ""])

            await self.mod_channel.send(self.code_format(report_str))
        return nextmsg


    async def on_ready(self):
        print(f'{self.user.name} has connected to Discord! It is these guilds:')
        for guild in self.guilds:
            print(f' - {guild.name}')
        print('Press Ctrl-C to quit.')

        # Parse the group number out of the bot's name
        match = re.search('[gG]roup (\d+) [bB]ot', self.user.name)
        if match:
            self.group_num = match.group(1)
        else:
            raise Exception("Group number not found in bot's name. Name format should be \"Group # Bot\".")

        # Find the mod channel in each guild that this bot should report to
        for guild in self.guilds:
            for channel in guild.text_channels:
                if channel.name == f'group-{self.group_num}-mod':
                    self.mod_channel = channel

    async def on_message(self, message):
        '''
        This function is called whenever a message is sent in a channel that the bot can see (including DMs). 
        Currently the bot is configured to only handle messages that are sent over DMs or in your group's "group-#" channel. 
        '''
        # # Hack to pin messages: uncomment the two lines below, and then the bot will pin any message sent.
        # # To unpin a message, just delete it.
        # await message.pin()
        # return

        # Ignore messages from the bot 
        if message.author.id == self.user.id:
            return

        # Check if this message was sent in a server ("guild") or if it's a DM
        if message.guild:
            await self.handle_channel_message(message)
        else:
            await self.handle_dm(message)

    async def handle_dm(self, message):
        # Handle a help message
        if message.content in Report.HELP_KEYWORDS:
            reply =  "Use the `report` command to begin the reporting process.\n"
            reply += "Use the `cancel` command to cancel the report process.\n"
            await message.channel.send(reply)
            return

        author_id = message.author.id
        responses = []

        # Only respond to messages if they're part of a reporting flow
        if author_id not in self.reports and not message.content.lower() in Report.START_KEYWORDS:
            return

        if message.author.id in self.malicious_reporter_ids:
            td = datetime.datetime.now()-self.malicious_reporter_ids[message.author.id]
            time_elapse = td.total_seconds() / 60
            if time_elapse < MALICIOUS_REPORTER_SUSPEND_TIME:
                reply = "Reporting feature is temporarily suspended for your account."
                await message.channel.send(reply)
                return

        # If we don't currently have an active report for this user, add one
        if author_id not in self.reports:
            self.reports[author_id] = Report(self)

        # Let the report class handle this message; forward all the messages it returns to uss
        responses = await self.reports[author_id].handle_message(message)
        for r in responses:
            await message.channel.send(r)

        # If the report is complete or cancelled, remove it from our map
        if self.reports[author_id].report_complete():
            self.reports.pop(author_id)

    def check_message_url_against_active_reports(self, author_id, message_url):
        # block the report from being submitted if the user already submitted a report on the same message
        if message_url in self.user_active_reports[author_id]["message_urls"]:
            return True
        return False

    def handle_user_report_submission(self, author_id, mod_report):
        # note down report stats
        timestamp = self.reports[author_id].get_timestamp()
        message_url = self.reports[author_id].get_message_url()
        self.user_active_reports[author_id]["timestamps"].append(timestamp)
        self.user_active_reports[author_id]["message_urls"].append(message_url)

        # add report to all active reports
        self.all_active_reports.append(ActiveReport(author_id, self.reports[author_id], timestamp, message_url))

        # help report submit to mod channel
        # TODO: can modify so a report from all_active_reports is sent to the moderators when the mod channel 
        # send a specific message instead of sending it immediately here.

        fm = ForwardedReport(mod_report["message"]["content"], mod_report["message"]["author_id"], mod_report["timestamp"],
                             reporter_account=author_id, mod_report = mod_report, scores = None, auto_flagged = False)

        immediate_danger = 1   #1:not immediate_danger
        if mod_report["immediate_danger"]:
            immediate_danger = 0
        self.review_queue.put(
            PrioritizedReport((immediate_danger, datetime.datetime.strptime(fm.report_time, "%Y-%m-%d %H:%M:%S.%f")), fm))

        return True, ""

    async def handle_channel_message(self, message):
        # Only handle messages sent in the "group-#" channel
        if not message.channel.name == f'group-{self.group_num}' and not message.channel.name == f'group-{self.group_num}-mod':
            return
        elif message.channel.name == f'group-{self.group_num}':
            scores = self.eval_text(message)
            print(message.content)
            print(scores)
            print()
            report_to_moderator = await self.eval_perspective_score(message, scores)
            await self.check_message_against_blacklist(message)
            if report_to_moderator:
                # Forward the message to the mod channel
                # await self.mod_channel.send(f'Suspicious Scam Message Forwarded to Moderator:\n{message.author.name}: "{message.content}"')
                mod_report = {}

                mod_report["message"] = {
                    "author_id": message.author.id,
                    "author": message.author.name,
                    "content": message.content,
                    "url": message.jump_url
                }
                fm = ForwardedReport(message.content, message.author.id,
                                     str(datetime.datetime.now()),
                                     reporter_account=None, mod_report=mod_report, scores=scores, auto_flagged=True)
                immediate_danger = 1
                self.review_queue.put(
                    PrioritizedReport((immediate_danger,datetime.datetime.strptime(fm.report_time, "%Y-%m-%d %H:%M:%S.%f")),fm))



        else:
            #moderator should input "next report"
            if message.content.lower() == "next report":
                if self.moderator_state == "Busy":
                    reply = "Please finish processing the current report before starting a new one.\n"
                    await message.channel.send(reply)
                    return
                self.moderator_state = "Busy"
                forwarded_message = await self.check_review_queue()
                if forwarded_message is None:
                    reply = "No more reports to be reviewed.\n"
                    await message.channel.send(reply)
                    self.moderator_state = "Free"
                else:
                    malicious = False
                    immediate_danger = False
                    escalate = False
                    if not forwarded_message.auto_flagged:
                        malicious = await self.check_malicious_user_report(forwarded_message, message.channel)
                    if malicious:
                        scam_message_url = forwarded_message.mod_report["message"]["url"]
                        scam_message_url = re.search('/(\d+)/(\d+)/(\d+)', scam_message_url)
                        guild = self.get_guild(int(scam_message_url.group(1)))
                        scam_message_channel = guild.get_channel(int(scam_message_url.group(2)))
                        scam_message = await scam_message_channel.fetch_message(int(scam_message_url.group(3)))
                        await scam_message.reactions[0].remove(self.user)
                        await self.mod_channel.send("Finished processing a malicious/frivolous user report")
                        self.moderator_state = "Free"
                        return
                    else:
                        immediate_danger = await self.check_immediate_danger(message.channel)
                    if immediate_danger:
                        scam_message_url = forwarded_message.mod_report["message"]["url"]
                        scam_message_url = re.search('/(\d+)/(\d+)/(\d+)', scam_message_url)
                        guild = self.get_guild(int(scam_message_url.group(1)))
                        scam_message_channel = guild.get_channel(int(scam_message_url.group(2)))
                        scam_message = await scam_message_channel.fetch_message(int(scam_message_url.group(3)))
                        await scam_message.reactions[0].remove(self.user)
                        await scam_message.add_reaction("🆘")  # the dm has been flagged with immediate danger
                        await self.mod_channel.send("Finished processing a report")
                        self.moderator_state = "Free"
                        return
                    else:
                        escalate = await self.check_escalate(message.channel)
                    if escalate:
                        scam_message_url = forwarded_message.mod_report["message"]["url"]
                        scam_message_url = re.search('/(\d+)/(\d+)/(\d+)', scam_message_url)
                        guild = self.get_guild(int(scam_message_url.group(1)))
                        scam_message_channel = guild.get_channel(int(scam_message_url.group(2)))
                        scam_message = await scam_message_channel.fetch_message(int(scam_message_url.group(3)))
                        await scam_message.reactions[0].remove(self.user)
                        await scam_message.add_reaction("👨‍💼")  # the dm has been escalated

                        await self.mod_channel.send("Finished processing a report")
                        self.moderator_state = "Free"
                        return
                    else:
                        #todo
                        newscamaddr =  await self.checkscamaddr(message.channel)
                        if newscamaddr is not None:
                            newscamaddr_trimmed = re.sub(r"^(https?:\/\/)?(www\.)?", "", newscamaddr).rstrip("/") # trims prefix for URLs
                            if newscamaddr_trimmed not in self.scamaddr:
                                self.scamaddr.add(newscamaddr_trimmed)
                                await self.mod_channel.send(
                                    "Added the reported scam URL/crypto address to the internal blacklist.")
                            else:
                                await self.mod_channel.send(
                                    "The reported scam URL/crypto address is already in the internal blacklist.")

                        await self.handleMessage(forwarded_message, message.channel)
                        await self.handleReportedAccount(forwarded_message, message.channel)
                        await self.mod_channel.send("Finished processing a report")
                        self.moderator_state = "Free"
                        return


    def eval_text(self, message):
        '''
        Evaluates a message using Perspective and our classifier and returns a dictionary of scores.
        '''
        PERSPECTIVE_URL = 'https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze'

        url = PERSPECTIVE_URL + '?key=' + self.perspective_key
        unidecoded_message_content = unidecode(message.content).lower()
        data_dict = {
            'comment': {'text': unidecoded_message_content},
            'languages': ['en'],
            'requestedAttributes': {
                                    'SEVERE_TOXICITY': {}, 'PROFANITY': {},
                                    'IDENTITY_ATTACK': {}, 'THREAT': {},
                                    'TOXICITY': {},
                                    #'FLIRTATION': {}
                                },
            'doNotStore': True
        }
        response = requests.post(url, data=json.dumps(data_dict))
        response_dict = response.json()

        scores = {}
        for attr in response_dict["attributeScores"]:
            scores[attr] = response_dict["attributeScores"][attr]["summaryScore"]["value"]

        # now eval using crypto scam classifier
        crypto_scam_proba = naive_bayes_classifier.get_predictions([unidecoded_message_content], 
                                                        classifier, vectorizer, predict_proba=True)[0][1]
        scores['CRYPTO_SCAM'] = crypto_scam_proba
        
        return scores

    async def eval_perspective_score(self, message, scores):
        '''
        Add profanity emoji to text if any attribute from Perspective is bigger than PROFANITY_THRESHOLD
        '''

        report_to_moderator = True
        safe = True

        for score in scores.values():
            if score > PROFANITY_THRESHOLD:
                safe = False
            if score > PROFANITY_THRESHOLD_Moderation:
                await message.add_reaction("🤬")
                report_to_moderator = False

        if not safe and report_to_moderator:
            await message.add_reaction("❓") #means send to moderator
            return True
        else:
            return False

    async def check_message_against_blacklist(self, message):
        '''
        Add web emoji to text if URL/address is in blacklist
        '''
        # Check for bitcoin addresses in blacklist. 
        bitcoin_regex = re.compile(r'\b([13][a-km-zA-HJ-NP-Z1-9]{25,34}|bc1[ac-hj-np-zAC-HJ-NP-Z02-9]{11,71})\b')
        bitcoin_addresses = bitcoin_regex.findall(message.content)
        url_regex = re.compile(r"((https?:\/\/)?(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*))")
        urls = url_regex.findall(message.content)

        message_contains_blacklist_item = False
        for addr in bitcoin_addresses:
            if addr in self.scamaddr:
                message_contains_blacklist_item = True
        for url in urls:
            url = url[0]
            url_trimmed = re.sub(r"^(https?:\/\/)?(www\.)?", "", url).rstrip("/")
            if url_trimmed in self.scamaddr:
                message_contains_blacklist_item = True
        if message_contains_blacklist_item:
            await message.add_reaction("🕸️")


    async def on_message_edit(self, before, after):
        '''
        Prevent editing message into abusive content
        '''
        if before.content != after.content:
            if after.guild:
                await self.handle_channel_message(after)
            else:
                reply = "Please do not edit your message to me!\n"
                reply += "Use the `cancel` command to cancel the report process and start over.\n"
                await after.channel.send(reply)

    def code_format(self, text):
        return "```" + text + "```"

    async def prompt_for_choice(self, choices, channel):
        reply = f"\n\nPlease enter a number between 1 and {len(choices)}:\n"
        for i, choice in enumerate(choices):
            reply += f"{i+1}) {choice}\n"
        await channel.send(reply)

        def check(msg):
            return msg.content.isnumeric() and 0 < int(msg.content) and int(msg.content) <= len(choices)

        msg = await self.wait_for("message", check=check)
        return int(msg.content)-1

    async def check_malicious_user_report(self, forwarded_message, channel):

        await channel.send("Is this a malicious/frivolous user report? Enter 'y' or 'n'.")

        def check(msg):
            return msg.content.lower() in {'y', 'n'}

        msg = await self.wait_for("message", check=check)
        if msg.content.lower() == 'y':
            await self.handle_malicious_user_report(forwarded_message, channel)
            return True
        else:
            #genuine report
            return False

    async def handle_malicious_user_report(self, forwarded_message, channel):
        malicious_user_id = forwarded_message.reporter_account
        malicious_report_channel_id = forwarded_message.mod_report["report_dm_channel_id"]
        await channel.send("Choose outcome for the malicious/frivolous reporter.")
        choices = [e.value for e in ReporterOutcomes]
        user_choice = await self.prompt_for_choice(choices, channel)
        reporteroutcome = ReporterOutcomes(choices[user_choice])

        if malicious_user_id not in self.malicious_reporter_strike:
            self.malicious_reporter_strike[malicious_user_id] = 0
        self.malicious_reporter_strike[malicious_user_id] += 1


        if reporteroutcome == ReporterOutcomes.WARN:
            await self.get_channel(malicious_report_channel_id).send("WARNING: please do not send malicious/frivolous reports!")
        else:
            assert reporteroutcome == ReporterOutcomes.SUSPEND
            self.malicious_reporter_ids[malicious_user_id] = datetime.datetime.now()
            await self.get_channel(malicious_report_channel_id).send("Your report feature will be suspended for "+
                                                                     str(MALICIOUS_REPORTER_SUSPEND_TIME)+ " minutes for "+
                                                                     "sending a malicious/frivolous report!", )

    async def check_immediate_danger(self, channel):

        await channel.send("Is there an immediate danger? Enter 'y' or 'n'.")

        def check(msg):
            return msg.content.lower() in {'y', 'n'}

        msg = await self.wait_for("message", check=check)
        if msg.content.lower() == 'y':
            await channel.send("MOCKED: Incident is reported to law enforcement! This report will be handled elsewhere. Thank you for reviewing.")
            return True
        else:
            return False

    async def check_escalate(self, channel):

        await channel.send("Would you like to escalate to higher-level reviewers? Enter 'y' or 'n'.")

        def check(msg):
            return msg.content.lower() in {'y', 'n'}

        msg = await self.wait_for("message", check=check)
        if msg.content.lower() == 'y':
            await channel.send("MOCKED: Incident is escalated to higher-level reviewers!")
            return True
        else:
            return False

    async def checkscamaddr(self, channel):
        url = None
        await channel.send("Does the message include a scam URL/crypto address? Enter 'y' or 'n'.")

        def check(msg):
            return msg.content.lower() in {'y', 'n'}

        msg = await self.wait_for("message", check=check)

        if msg.content.lower() == 'y':
            await channel.send("Please enter the reported scam URL/Bitcoin address to be added to the internal blacklist. Please only enter valid Bitcoin addresses and URLs, or else they will not be recognized during auto-flagging!")
            msg = await self.wait_for("message")
            url = msg.content
        return url

    async def handleMessage(self, forwarded_message, channel):
        await channel.send("Choose outcome for the reported content.")
        choices = [e.value for e in DMOutcomes]
        user_choice = await self.prompt_for_choice(choices, channel)
        dmoutcome = DMOutcomes(choices[user_choice])

        scam_message_url = forwarded_message.mod_report["message"]["url"]
        scam_message_url = re.search('/(\d+)/(\d+)/(\d+)', scam_message_url)
        guild = self.get_guild(int(scam_message_url.group(1)))
        scam_message_channel = guild.get_channel(int(scam_message_url.group(2)))
        scam_message = await scam_message_channel.fetch_message(int(scam_message_url.group(3)))

        await scam_message.reactions[0].remove(self.user)

        if dmoutcome == DMOutcomes.FLAG:
            await scam_message.add_reaction("‼️")  # the dm has been flagged



    async def handleReportedAccount(self, forwarded_message, channel):
        await channel.send("Choose outcome for the reported account.")
        choices = [e.value for e in ReportedAccOutcomes]
        user_choice = await self.prompt_for_choice(choices, channel)
        ReportedAccountOut  = ReportedAccOutcomes(choices[user_choice])
        scammer_id = forwarded_message.reported_account

        if ReportedAccountOut != ReportedAccOutcomes.NOACTION:
            if scammer_id not in self.abusive_reported_acc_strike:
                self.abusive_reported_acc_strike[scammer_id] = 0
            self.abusive_reported_acc_strike[scammer_id] += 1


        if ReportedAccountOut == ReportedAccOutcomes.TEMPDEACTSHORT:
            scammer = await self.fetch_user(scammer_id)
            await scammer.send("WARNING: please do not send scam messages. " +
                          "Your account will be temporarily deactivated for " + str(SCAMMER_DEACT_TIME_SHORT) + " days.")
        elif ReportedAccountOut == ReportedAccOutcomes.TEMPDEACTLONG:
            scammer = await self.fetch_user(scammer_id)
            await scammer.send("WARNING: please do not send scam messages. " +
                          "Your account will be temporarily deactivated for " + str(SCAMMER_DEACT_TIME_LONG) + " days.")
        elif ReportedAccountOut == ReportedAccOutcomes.PERMANENTLYDEACT:
            scammer = await self.fetch_user(scammer_id)
            await scammer.send("WARNING: please do not send scam messages. " +
                          "Your account will be permanently deactivated.")




class ReporterOutcomes(Enum):
    WARN = "Warn the reporter for malicious/frivolous reports."
    SUSPEND = "Suspend the report feature for the reporter account."

class DMOutcomes(Enum):
    NOACTION = "False Alarm: No action."
    FLAG = "Scam Message: Flag Message."

class ReportedAccOutcomes(Enum):
    NOACTION = "False Alarm: No action."
    TEMPDEACTSHORT = "Low Severity: Temporarily deactivate reported account for a short period and warn."
    TEMPDEACTLONG = "Medium Severity: Temporarily deactivate reported account for a longer period and warn."
    PERMANENTLYDEACT = "High Severity: Permanently deactivate reported account."



client = ModBot(perspective_key)
client.run(discord_token)
