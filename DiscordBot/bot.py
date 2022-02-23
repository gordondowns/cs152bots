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
import pickle
from crypto_scam_classifier import naive_bayes_classifier

# Thresholds
PROFANITY_THRESHOLD = 0.5

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
    priority: datetime
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

    def fmtodict(self):
        fmdict = {}
        fmdict["reported_content"] = self.reported_content
        fmdict["reported_account"] = self.reported_account
        fmdict["report_time"] = self.report_time

        fmdict["reporter_account"] = self.reporter_account
        fmdict["mod_report"] = self.mod_report
        fmdict["scores"] = self.scores
        fmdict["auto_flagged"] = self.auto_flagged
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

    async def handle_user_report_submission(self, author_id, mod_report):
        # block the report from being submitted if the user already submitted a report on the same message
        # TODO: can add more conditions
        if self.reports[author_id].get_message_url() in self.user_active_reports[author_id]["message_urls"]:
            return False, "you have already submitted a report on this message"

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

        self.review_queue.put(
            PrioritizedReport(datetime.datetime.strptime(fm.report_time, "%Y-%m-%d %H:%M:%S.%f"), fm))
        # TODO:only send the message at the top of the PQ, and send another when the current one HAS BEEN PROCESSED
        await self.mod_channel.send(self.code_format(json.dumps(fm.fmtodict(), indent=2)))
        return True, ""

    async def handle_channel_message(self, message):
        # Only handle messages sent in the "group-#" channel
        if not message.channel.name == f'group-{self.group_num}' and not message.channel.name == f'group-{self.group_num}-mod':
            return
        elif message.channel.name == f'group-{self.group_num}':
            scores = self.eval_text(message)
            auto_flag = await self.eval_perspective_score(message, scores)
            if auto_flag:
                # Forward the message to the mod channel
                # await self.mod_channel.send(f'Suspicious Scam Message Forwarded to Moderator:\n{message.author.name}: "{message.content}"')
                fm = ForwardedReport(message.content, message.author.id,
                                     str(datetime.datetime.now()),
                                     reporter_account=None, mod_report=None, scores=scores, auto_flagged=True)
                self.review_queue.put(
                    PrioritizedReport(datetime.datetime.strptime(fm.report_time, "%Y-%m-%d %H:%M:%S.%f"),fm))

                #TODO:only send the message at the top of the PQ, and send another when the current one HAS BEEN PROCESSED
                await self.mod_channel.send(self.code_format(json.dumps(fm.fmtodict(), indent=2)))
        else:
            #message forwarded to mod channel for manual review
            forwarded_message_content = json.loads(message.content)
            forwarded_message = dicttofm(forwarded_message_content)
            #TODO: CONTINUE HERE


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
                                    'TOXICITY': {}, 'FLIRTATION': {}
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

        for score in scores.values():
            if score > PROFANITY_THRESHOLD:
                await message.add_reaction("🤬")
                return True

        return False

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


client = ModBot(perspective_key)
client.run(discord_token)
