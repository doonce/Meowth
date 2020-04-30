import asyncio
import copy
import re
import time
import datetime
from dateutil.relativedelta import relativedelta
import dateparser
import urllib
import textwrap
import logging
import string
import os
import json
import random
import functools
import itertools
import traceback

import discord
from discord.ext import commands, tasks

import meowth
from meowth import checks
from meowth.exts import pokemon as pkmn_class
from meowth.exts import utilities as utils

logger = logging.getLogger("meowth")

class Huntr(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.huntr_cleanup.start()
        self.raidhour_check.start()
        self.event_loop = asyncio.get_event_loop()
        self.bot.active_raidhours = []

    def cog_unload(self):
        self.huntr_cleanup.cancel()
        self.raidhour_check.cancel()
        for task in asyncio.Task.all_tasks():
            if "raidhour_manager" in str(task) and "huntr" in str(task):
                task.cancel()

    @tasks.loop(seconds=600)
    async def huntr_cleanup(self, loop=True):
        logger.info('------ BEGIN ------')
        for guild in list(self.bot.guilds):
            if guild.id not in list(self.bot.guild_dict.keys()):
                continue
            try:
                report_edit_dict = {}
                report_delete_dict = {}
                for report_dict in ['pokealarm_dict', 'pokehuntr_dict']:
                    try:
                        alarm_dict = self.bot.guild_dict[guild.id].setdefault(report_dict, {})
                        for reportid in list(alarm_dict.keys()):
                            if alarm_dict.get(reportid, {}).get('exp', 0) <= time.time():
                                report_channel = self.bot.get_channel(alarm_dict.get(reportid, {}).get('report_channel'))
                                if report_channel:
                                    user_report = alarm_dict.get(reportid, {}).get('report_message', None)
                                    if user_report:
                                        report_delete_dict[user_report] = {"action":"delete", "channel":report_channel}
                                    cleanup_setting = self.bot.guild_dict[guild.id].get('configure_dict', {}).get('scanners', {}).setdefault('cleanup_setting', "edit")
                                    if cleanup_setting == "delete":
                                        report_delete_dict[reportid] = {"action":"delete", "channel":report_channel}
                                    else:
                                        report_edit_dict[reportid] = {"action":alarm_dict.get(reportid, {}).get('expedit', ''), "channel":report_channel}
                                    if alarm_dict.get(reportid, {}).get('dm_dict', False):
                                        self.bot.loop.create_task(utils.expire_dm_reports(self.bot, alarm_dict.get(reportid, {}).get('dm_dict', {})))
                                try:
                                    del self.bot.guild_dict[guild.id][report_dict][reportid]
                                except KeyError:
                                    pass
                    except:
                        pass
                for messageid in report_delete_dict.keys():
                    try:
                        report_message = await report_delete_dict[messageid]['channel'].fetch_message(messageid)
                        await utils.safe_delete(report_message)
                    except:
                        pass
                for messageid in report_edit_dict.keys():
                    try:
                        report_message = await report_edit_dict[messageid]['channel'].fetch_message(messageid)
                        if isinstance(report_message.embeds[0].colour, discord.embeds._EmptyEmbed):
                            colour = discord.Colour.lighter_grey()
                        else:
                            colour = report_message.embeds[0].colour.value
                        await report_message.edit(content=report_edit_dict[messageid]['action']['content'], embed=discord.Embed(description=report_edit_dict[messageid]['action'].get('embedcontent'), colour=colour))
                        await report_message.clear_reactions()
                    except:
                        pass
            except Exception as e:
                print(traceback.format_exc())
        # save server_dict changes after cleanup
        logger.info('SAVING CHANGES')
        try:
            await self.bot.save
        except Exception as err:
            logger.info('SAVING FAILED' + err)
        logger.info('------ END ------')
        if not loop:
            return

    @huntr_cleanup.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

    """Handlers"""

    @commands.Cog.listener()
    async def on_message(self, message):
        ctx = await self.bot.get_context(message)
        if not ctx.guild or ctx.guild.id not in list(self.bot.guild_dict.keys()):
            return
        if (ctx.author.bot or message.webhook_id or ctx.author.id in self.bot.managers or ctx.author.id == self.bot.owner) and ctx.author != ctx.guild.me:
            if message.content.lower().startswith("!alarm") and "{" in message.content:
                await self.on_pokealarm(ctx)
        if (str(ctx.author) == 'GymHuntrBot#7279') or (str(ctx.author) == 'HuntrBot#1845'):
            await self.on_huntr(ctx)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        channel = self.bot.get_channel(payload.channel_id)
        guild = getattr(channel, "guild", None)
        if guild and guild.id not in list(self.bot.guild_dict.keys()):
            return
        try:
            user = self.bot.get_user(payload.user_id)
        except AttributeError:
            return
        if user == self.bot.user:
            return
        if guild:
            user = guild.get_member(payload.user_id)
        else:
            return
        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.errors.NotFound, AttributeError, discord.Forbidden):
            return
        ctx = await self.bot.get_context(message)
        pokealarm_dict = copy.deepcopy(ctx.bot.guild_dict[channel.guild.id].get('pokealarm_dict', {}))
        pokehuntr_dict = copy.deepcopy(ctx.bot.guild_dict[channel.guild.id].get('pokehuntr_dict', {}))
        raid_cog = self.bot.cogs.get('Raid')
        if raid_cog and message.id in pokealarm_dict.keys() and not user.bot:
            if str(payload.emoji) == self.bot.custom_emoji.get('huntr_report', u'\U00002705'):
                await self.on_pokealarm(ctx, user)
            elif str(payload.emoji) == self.bot.custom_emoji.get('raid_maybe', u'\U00002753'):
                raid_channel = await self.on_pokealarm(ctx, user)
                ctx.message.author, ctx.author = user, user
                ctx.channel, ctx.message.channel = raid_channel, raid_channel
                await raid_cog._rsvp(ctx, "maybe", "1")
            elif str(payload.emoji) == self.bot.custom_emoji.get('raid_omw', u'\U0001f3ce\U0000fe0f'):
                raid_channel = await self.on_pokealarm(ctx, user)
                ctx.message.author, ctx.author = user, user
                ctx.channel, ctx.message.channel = raid_channel, raid_channel
                await raid_cog._rsvp(ctx, "coming", "1")
            elif str(payload.emoji) == self.bot.custom_emoji.get('raid_here', u'\U0001F4CD'):
                raid_channel = await self.on_pokealarm(ctx, user)
                ctx.message.author, ctx.author = user, user
                ctx.channel, ctx.message.channel = raid_channel, raid_channel
                await raid_cog._rsvp(ctx, "here", "1")
            elif str(payload.emoji) == self.bot.custom_emoji.get('raid_report', u'\U0001F4E2'):
                ctx = await self.bot.get_context(message)
                ctx.author, ctx.message.author = user, user
                await utils.remove_reaction(message, payload.emoji, user)
                return await ctx.invoke(self.bot.get_command('raid'))
            elif str(payload.emoji) == self.bot.custom_emoji.get('list_emoji', u'\U0001f5d2\U0000fe0f'):
                ctx = await self.bot.get_context(message)
                await asyncio.sleep(0.25)
                await utils.remove_reaction(message, payload.emoji, self.bot.user)
                await asyncio.sleep(0.25)
                await utils.remove_reaction(message, payload.emoji, user)
                await ctx.invoke(self.bot.get_command("list pokealarms"), type="pokealarm")
                await asyncio.sleep(5)
                await utils.add_reaction(message, payload.emoji)
        elif raid_cog and message.id in pokehuntr_dict.keys() and not user.bot:
            if str(payload.emoji) == self.bot.custom_emoji.get('huntr_report', u'\U00002705'):
                await self.on_huntr(ctx, user)
            elif str(payload.emoji) == self.bot.custom_emoji.get('raid_maybe', u'\U00002753'):
                raid_channel = await self.on_huntr(ctx, user)
                ctx.message.author, ctx.author = user, user
                ctx.channel, ctx.message.channel = raid_channel, raid_channel
                await raid_cog._rsvp(ctx, "maybe", "1")
            elif str(payload.emoji) == self.bot.custom_emoji.get('raid_omw', u'\U0001f3ce\U0000fe0f'):
                raid_channel = await self.on_huntr(ctx, user)
                ctx.message.author, ctx.author = user, user
                ctx.channel, ctx.message.channel = raid_channel, raid_channel
                await raid_cog._rsvp(ctx, "coming", "1")
            elif str(payload.emoji) == self.bot.custom_emoji.get('raid_here', u'\U0001F4CD'):
                raid_channel = await self.on_huntr(ctx, user)
                ctx.message.author, ctx.author = user, user
                ctx.channel, ctx.message.channel = raid_channel, raid_channel
                await raid_cog._rsvp(ctx, "here", "1")
            elif str(payload.emoji) == self.bot.custom_emoji.get('raid_report', u'\U0001F4E2'):
                ctx = await self.bot.get_context(message)
                ctx.author, ctx.message.author = user, user
                await utils.remove_reaction(message, payload.emoji, user)
                return await ctx.invoke(self.bot.get_command('raid'))
            elif str(payload.emoji) == self.bot.custom_emoji.get('list_emoji', u'\U0001f5d2\U0000fe0f'):
                ctx = await self.bot.get_context(message)
                await asyncio.sleep(0.25)
                await utils.remove_reaction(message, payload.emoji, self.bot.user)
                await asyncio.sleep(0.25)
                await utils.remove_reaction(message, payload.emoji, user)
                await ctx.invoke(self.bot.get_command("list pokealarms"), type="huntr")
                await asyncio.sleep(5)
                await utils.add_reaction(message, payload.emoji)

    # DEPRACATED UNTIL POKEHUNTR RETURNS
    # async def on_huntr(self, ctx, reactuser=None):
    #     message = ctx.message
    #     timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))).strftime('%I:%M %p')
    #     now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
    #     auto_raid = self.bot.guild_dict[message.guild.id]['configure_dict'].get('scanners', {})['reports'].get('raid', False)
    #     auto_egg = self.bot.guild_dict[message.guild.id]['configure_dict'].get('scanners', {})['reports'].get('egg', False)
    #     auto_wild = self.bot.guild_dict[message.guild.id]['configure_dict'].get('scanners', {})['reports'].get('wild', False)
    #     raid_channel = None
    #     maybe_reaction = self.bot.custom_emoji.get('raid_maybe', u'\U00002753')
    #     omw_reaction = self.bot.custom_emoji.get('raid_omw', u'\U0001f3ce\U0000fe0f')
    #     here_reaction = self.bot.custom_emoji.get('raid_here', u'\U0001F4CD')
    #     report_emoji = self.bot.custom_emoji.get('raid_report', u'\U0001F4E2')
    #     list_emoji = ctx.bot.custom_emoji.get('list_emoji', u'\U0001f5d2\U0000fe0f')
    #     react_list = [maybe_reaction, omw_reaction, here_reaction, report_emoji, list_emoji]
    #     if not auto_raid and not auto_egg and not auto_wild:
    #         return
    #     if not reactuser:
    #         #get gps
    #         if message.embeds and (message.author.id == 329412230481444886 or message.author.id == 295116861920772098 or message.author.id == message.guild.me.id):
    #             raid_cog = self.bot.cogs.get('Raid')
    #             if not raid_cog:
    #                 logger.error("Raid Cog not loaded")
    #                 return
    #             huntrgps = ""
    #             try:
    #                 huntrgps = message.embeds[0].url.split('#')[1]
    #             except IndexError:
    #                 req = urllib.request.Request(message.embeds[0].url, headers={'User-Agent': 'Magic Browser'})
    #                 con = urllib.request.urlopen(req)
    #                 try:
    #                     huntrgps = con.geturl().split('#')[1]
    #                     con.close()
    #                 except IndexError:
    #                     source = str(con.read().decode('utf8').replace('\n', '').replace(' ', ''))
    #                     sourceindex = source.find('huntr.com/#')
    #                     newsourceindex = source.rfind('http', 0, sourceindex)
    #                     newsourceend = source.find('"', newsourceindex)
    #                     newsource = source[newsourceindex:newsourceend]
    #                     huntrgps = newsource.split('#')[1]
    #                     con.close()
    #             if not huntrgps:
    #                 return
    #         if (message.author.id == 329412230481444886 or message.author.id == message.guild.me.id) and message.embeds:
    #             if (len(message.embeds[0].title.split(' ')) == 5) and auto_raid:
    #                 match = re.search('[* ]*([a-zA-Z ]*)[* .]*\n(.*)\n[* CP:]*([0-9]*)[ \-*Moves:]*(.*)\n[*a-zA-Z: ]*([0-2])[ a-z]*([0-9]*)[ a-z]*([0-9]*)', message.embeds[0].description)
    #                 reporttype = "raid"
    #                 raid_details = match.group(1).strip()
    #                 entered_raid = match.group(2).lower()
    #                 moveset = match.group(4)
    #                 raidexp = match.group(6)
    #                 egg_level = 0
    #                 await utils.safe_delete(message)
    #                 egg_level = utils.get_level(self.bot, entered_raid)
    #                 if egg_level.isdigit() and int(egg_level) in self.bot.guild_dict[message.guild.id]['configure_dict'].get('scanners', {})['raidlvls']:
    #                     auto_report = True
    #                 elif egg_level == "EX" and "EX" in self.bot.guild_dict[message.guild.id]['configure_dict'].get('scanners', {})['raidlvls']:
    #                     auto_report = True
    #                 else:
    #                     auto_report = False
    #                 auto_report = True if int(utils.get_level(self.bot, entered_raid)) in self.bot.guild_dict[message.guild.id]['configure_dict'].get('scanners', {})['raidlvls'] else False
    #             elif (len(message.embeds[0].title.split(' ')) == 6) and auto_egg:
    #                 match = re.search('[* ]*([a-zA-Z ]*)[* .]*\n[*:a-zA-Z ]*([0-2]*)[ a-z]*([0-9]*)[ a-z]*([0-9]*)', message.embeds[0].description)
    #                 reporttype = "egg"
    #                 egg_level = message.embeds[0].title.split(' ')[1]
    #                 raid_details = match.group(1).strip()
    #                 raidexp = match.group(3)
    #                 entered_raid = None
    #                 moveset = False
    #                 await utils.safe_delete(message)
    #                 auto_report = True if int(egg_level) in self.bot.guild_dict[message.guild.id]['configure_dict'].get('scanners', {})['egglvls'] else False
    #             for channelid in self.bot.guild_dict[message.guild.id]['raidchannel_dict']:
    #                 channel_gps = self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid].get('coordinates', None)
    #                 channel_address = self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid].get('address', None)
    #                 if not channel_gps:
    #                     continue
    #                 if channel_gps == huntrgps or channel_address == raid_details:
    #                     channel = self.bot.get_channel(channelid)
    #                     if self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid]['type'] == 'egg':
    #                         await raid_cog._eggtoraid(entered_raid.lower().strip(), channel, author=message.author, moveset=moveset)
    #                     raidmsg = await channel.fetch_message(self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid]['raid_message'])
    #                     return
    #             if auto_report and reporttype == "raid":
    #                 report_details = {
    #                     "pokemon":entered_raid,
    #                     "gym":raid_details,
    #                     "raidexp":raidexp,
    #                     "gps":huntrgps,
    #                     "moves":moveset
    #                 }
    #                 await self.huntr_raid(ctx, report_details)
    #             elif auto_report and reporttype == "egg":
    #                 report_details = {
    #                     "level":egg_level,
    #                     "gym":raid_details,
    #                     "raidexp":raidexp,
    #                     "gps":huntrgps
    #                 }
    #                 await self.huntr_raidegg(ctx, report_details)
    #             elif reporttype == "raid":
    #                 gym_matching_cog = self.bot.cogs.get('GymMatching')
    #                 if gym_matching_cog:
    #                     test_gym = await gym_matching_cog.find_nearest_gym((huntrgps.split(",")[0], huntrgps.split(",")[1]), message.guild.id)
    #                     if test_gym:
    #                         raid_details = test_gym
    #                 raid_embed = await self.make_raid_embed(ctx, {'pkmn_obj':entered_raid, 'address':raid_details, 'coordinates':huntrgps, 'moves':moveset}, raidexp)
    #                 if not raid_embed:
    #                     return
    #                 pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, entered_raid)
    #                 pokehuntr_dict = self.bot.guild_dict[message.guild.id].setdefault('pokehuntr_dict', {})
    #                 ctx.raidreport = await message.channel.send(content=f"Meowth! {entered_raid.title()} raid reported by {message.author.mention}! Details: {raid_details}. React if you want to make a channel for this raid! Use {report_emoji} to report new, or {list_emoji} to list unreported raids!", embed=raid_embed)
    #                 await asyncio.sleep(0.25)
    #                 await utils.add_reaction(ctx.raidreport, self.bot.custom_emoji.get('huntr_report', u'\U00002705'))
    #                 for reaction in react_list:
    #                     await utils.add_reaction(ctx.raidreport, reaction)
    #                 dm_dict = {}
    #                 dm_dict = await raid_cog.send_dm_messages(ctx, raid_details, str(pokemon), f"Meowth! {entered_raid.title()} raid reported by {message.author.display_name} in {message.channel.mention}! Details: {raid_details}. React in {message.channel.mention} to report this raid!", copy.deepcopy(raid_embed), dm_dict)
    #                 self.bot.guild_dict[message.guild.id]['pokehuntr_dict'][ctx.raidreport.id] = {
    #                     "exp":time.time() + (int(raidexp) * 60),
    #                     "raidexp":raidexp,
    #                     'expedit': {"content":ctx.raidreport.content.split(" React")[0], "embedcontent":_('**This {pokemon} raid has expired!**').format(pokemon=entered_raid)},
    #                     "reporttype":"raid",
    #                     'report_channel':message.channel.id,
    #                     "level":0,
    #                     "pokemon":entered_raid,
    #                     "reporttime":now,
    #                     "gym":raid_details,
    #                     "gps":huntrgps,
    #                     "moves":moveset,
    #                     "embed":raid_embed,
    #                     "dm_dict": dm_dict
    #                 }
    #             elif reporttype == "egg":
    #                 gym_matching_cog = ctx.bot.cogs.get('GymMatching')
    #                 if gym_matching_cog:
    #                     test_gym = await gym_matching_cog.find_nearest_gym((huntrgps.split(",")[0], huntrgps.split(",")[1]), message.guild.id)
    #                     if test_gym:
    #                         raid_details = test_gym
    #                 raid_embed = await raid_cog.make_raid_embed(ctx, {'egg_level':egg_level, 'address':raid_details, 'coordinates': huntrgps}, raidexp)
    #                 if not raid_embed:
    #                     return
    #                 pokehuntr_dict = self.bot.guild_dict[message.guild.id].setdefault('pokehuntr_dict', {})
    #                 ctx.raidreport = await message.channel.send(content=f"Meowth! Level {egg_level} raid egg reported by {message.author.mention}! Details: {raid_details}. React if you want to make a channel for this raid! Use {report_emoji} to report new, or {list_emoji} to list unreported raids!", embed=raid_embed)
    #                 await asyncio.sleep(0.25)
    #                 await utils.add_reaction(ctx.raidreport, self.bot.custom_emoji.get('huntr_report', u'\U00002705'))
    #                 for reaction in react_list:
    #                     await utils.add_reaction(ctx.raidreport, reaction)
    #                 dm_dict = {}
    #                 dm_dict = await raid_cog.send_dm_messages(ctx, str(egg_level), raid_details, f"Meowth! Level {egg_level} raid egg reported by {message.author.display_name} in {message.channel.mention}! Details: {raid_details}. React in {message.channel.mention} to report this raid!", copy.deepcopy(raid_embed), dm_dict)
    #                 self.bot.guild_dict[message.guild.id]['pokehuntr_dict'][ctx.raidreport.id] = {
    #                     "exp":time.time() + (int(raidexp) * 60),
    #                     "raidexp":raidexp,
    #                     'expedit': {"content":ctx.raidreport.content.split(" React")[0], "embedcontent": _('**This level {level} raid egg has hatched!**').format(level=egg_level)},
    #                     "reporttype":"egg",
    #                     "report_channel":message.channel.id,
    #                     "level":egg_level,
    #                     "pokemon":None,
    #                     "reporttime":now,
    #                     "gym":raid_details,
    #                     "gps":huntrgps,
    #                     "moves":None,
    #                     "embed":raid_embed,
    #                     "dm_dict":dm_dict
    #                 }
    #         if (message.author.id == 295116861920772098 or message.author.id == message.guild.me.id) and message.embeds and auto_wild:
    #             wild_cog = self.bot.cogs.get('Wild')
    #             if not wild_cog:
    #                 logger.error("Wild Cog not loaded")
    #                 return
    #             reporttype = "wild"
    #             hpokeid = message.embeds[0].title.split(' ')[2].lower()
    #             hdesc = message.embeds[0].description.splitlines()
    #             hexpire = None
    #             hweather = None
    #             hiv = None
    #             huntrgps = "https://pokehuntr.com/#{huntrgps}".format(huntrgps=huntrgps)
    #             for line in hdesc:
    #                 if "remaining:" in line.lower():
    #                     hexpire = line.split(': ')[1][:(- 1)]
    #                 if "weather:" in line.lower():
    #                     hweather = line.split(': ')[1][1:(- 1)]
    #                 if "iv:" in line.lower():
    #                     hiv = line.split(': ')[1][2:(-2)].replace("%", "")
    #             hextra = "Weather: {hweather}".format(hweather=hweather)
    #             if hiv:
    #                 hextra += " / IV: {hiv}".format(hiv=hiv)
    #             await utils.safe_delete(message)
    #             huntr_details = {"pokemon":hpokeid, "coordinates":huntrgps, "expire":hexpire, "weather":hweather, "iv_percent":hiv}
    #             await self.huntr_wild(ctx, huntr_details, reporter="huntr")
    #             return
    #     else:
    #         raid_cog = self.bot.cogs.get('Raid')
    #         if not raid_cog:
    #             logger.error("Raid Cog not loaded")
    #             return
    #         await utils.safe_delete(message)
    #         pokehuntr_dict = copy.deepcopy(self.bot.guild_dict[message.guild.id].get('pokehuntr_dict', {}))
    #         reporttime = pokehuntr_dict[message.id]['reporttime']
    #         reporttype = pokehuntr_dict[message.id]['reporttype']
    #         coordinates = pokehuntr_dict[message.id]['gps']
    #         raid_details = pokehuntr_dict[message.id]['gym'].strip()
    #         dm_dict = copy.deepcopy(pokehuntr_dict[message.id]['dm_dict'])
    #         reacttime = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
    #         timediff = relativedelta(reacttime, reporttime)
    #         raidexp = int(reporttime.minute) - int(timediff.minutes)
    #         if reporttype == "egg":
    #             egg_level = pokehuntr_dict[message.id]['level']
    #             report_details = {
    #                 "level":egg_level,
    #                 "gym":raid_details,
    #                 "raidexp":raidexp,
    #                 "gps":coordinates
    #             }
    #             raid_channel = await self.huntr_raidegg(ctx, report_details, report_user=reactuser, dm_dict=dm_dict)
    #             return raid_channel
    #         elif reporttype == "raid":
    #             entered_raid = pokehuntr_dict[message.id]['pokemon']
    #             moveset = pokehuntr_dict[message.id]['moves']
    #             report_details = {
    #                 "pokemon":entered_raid,
    #                 "gym":raid_details,
    #                 "raidexp":raidexp,
    #                 "gps":coordinates,
    #                 "moves":moveset
    #             }
    #             raid_channel = await self.huntr_raid(ctx, report_details, report_user=reactuser, dm_dict=dm_dict)
    #             return raid_channel

    async def on_pokealarm(self, ctx, reactuser=None):
        """Requires a specific message.content format, which is "content" in PokeAlarm
        If an option is not available, replace <variable> with None
        Raid format = !alarm {"type":"raid", "pokemon":"[form] <pokemon name>", "gps":"<longitude>,<latitude>", "gym":"<gym name>", "raidexp":"<end minutes>", "moves":"<move name 1> / <move name 2>"}
        Raidegg format = !alarm {"type":"egg", "level":"<raid_level>", "gps":"<longitude>,<latitude>", "gym":"<gym name>", "raidexp":"<hatch minutes>"}
        Wild format (without IV) = !alarm {"type":"wild", "pokemon":"[gender] [form] <pokemon name>", "coordinates":"<latitude>,<longitude>, "weather":"[weather boost]", "expire":"[minutes] min [seconds] sec"}
        Wild format (with IV) = !alarm {"type":"wild", "pokemon":"[gender] [form] <pokemon name>", "gps":"<latitude>,<longitude>, "weather":"[weather boost]", "iv_percent":"[iv percentage]", "iv_long":"[long IV A/D/S]", "level":"[level]", "cp":"<cp>", "gender":"[gender]", "height":"[height]", "weight":"[weight]", "moveset":"[move name 1] / [move name 2]", "expire":"[minutes] min [seconds] sec"}
        Quest format = !alarm {"type":"research", "pokestop":"<stop name>", "gps":"<longitude>,<latitude>", "quest":"<quest task>", "reward":"<quest reward>"}
        Fill in everything within <> (required) and [] (optional) based on however your bot reports it."""
        message = ctx.message
        raid_channel = False
        pokealarm_dict = self.bot.guild_dict[ctx.guild.id].setdefault('pokealarm_dict', {})
        dm_dict = {}
        huntr_emoji = self.bot.custom_emoji.get('huntr_report', u'\U00002705')
        maybe_reaction = self.bot.custom_emoji.get('raid_maybe', u'\U00002753')
        omw_reaction = self.bot.custom_emoji.get('raid_omw', u'\U0001f3ce\U0000fe0f')
        here_reaction = self.bot.custom_emoji.get('raid_here', u'\U0001F4CD')
        report_emoji = self.bot.custom_emoji.get('raid_report', u'\U0001F4E2')
        list_emoji = ctx.bot.custom_emoji.get('list_emoji', u'\U0001f5d2\U0000fe0f')
        react_list = [huntr_emoji, maybe_reaction, omw_reaction, here_reaction, report_emoji, list_emoji]
        if not reactuser:
            reporttype = None
            report = None
            raidhour = False
            embed = message.embeds[0] if message.embeds else None
            utcnow = datetime.datetime.utcnow()
            now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
            message.content = message.content.replace("!alarm","").strip()
            await utils.safe_delete(message)
            try:
                report_details = json.loads(message.content)
            except:
                return
            if ctx.channel.id in self.bot.guild_dict[ctx.guild.id].get('configure_dict', {}).get('scanners', {}).get('forwarding', {}):
                send_to_channel = self.bot.get_channel(self.bot.guild_dict[ctx.guild.id]['configure_dict']['scanners']['forwarding'][ctx.channel.id])
                if not send_to_channel:
                    send_to_channel = ctx.channel
            else:
                send_to_channel = ctx.channel
            ctx.channel = send_to_channel
            if report_details.get('type', None) == "raid" or report_details.get('type', None) == "egg":
                raid_cog = self.bot.cogs.get('Raid')
                if not raid_cog:
                    logger.error("Raid Cog not loaded")
                    return
                alarm_pokemon = report_details.get('pokemon', None)
                alarm_egglevel = report_details.get('level', None)
                if alarm_pokemon:
                    alarm_egglevel = utils.get_level(self.bot, alarm_pokemon)
                    alarm_egglevel = int(alarm_egglevel) if alarm_egglevel else None
                for event in self.bot.guild_dict[ctx.guild.id].setdefault('raidhour_dict', {}):
                    if not alarm_egglevel:
                        break
                    if time.time() >= self.bot.guild_dict[ctx.guild.id]['raidhour_dict'][event]['mute_time'] and self.bot.guild_dict[ctx.guild.id]['raidhour_dict'][event]['event_end'] >= time.time():
                        if ctx.author.id == self.bot.guild_dict[ctx.guild.id]['raidhour_dict'][event]['bot_account'] and ctx.channel.id == self.bot.guild_dict[ctx.guild.id]['raidhour_dict'][event]['bot_channel']:
                            if self.bot.guild_dict[ctx.guild.id]['raidhour_dict'][event].get('egg_level', [0]) == [0] or alarm_egglevel in self.bot.guild_dict[ctx.guild.id]['raidhour_dict'][event].get('egg_level', [0]):
                                raidhour = True
                for channelid in self.bot.guild_dict[message.guild.id]['raidchannel_dict']:
                    channel_gps = self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid].get('coordinates', None)
                    channel_address = self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid].get('address', None)
                    channel_level = self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid].get('egg_level', None)
                    channel_type = self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid].get('type', None)
                    channel_meetup = self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid].get('meetup', {})
                    channel_exp = self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid].get('exp', time.time())
                    if channel_level == "EX" or channel_meetup:
                        continue
                    if (channel_level == "0" and channel_exp <= time.time()) or (channel_level == "0" and report_details.get('type', None) == "egg"):
                        continue
                    if channel_gps == report_details.get('gps', None) or channel_address == report_details.get('gym', None):
                        channel = self.bot.get_channel(channelid)
                        if embed and channel:
                            await channel.send(embed=embed)
                        if channel_type == 'egg':
                            if not utils.get_level(self.bot, report_details.get('pokemon', None)):
                                pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, report_details.get('pokemon', None))
                                if not pokemon:
                                    return
                                if str(pokemon) not in self.bot.raid_list:
                                    old_raid_dict = {}
                                    for raid_level in self.bot.raid_info['raid_eggs']:
                                        old_raid_dict[raid_level] = self.bot.raid_info['raid_eggs'][raid_level]['pokemon']
                                    with open(os.path.join('data', 'raid_info.json'), 'r') as fd:
                                        data = json.load(fd)
                                    data['raid_eggs'][channel_level]['pokemon'].append(str(pokemon))
                                    with open(os.path.join('data', 'raid_info.json'), 'w') as fd:
                                        json.dump(data, fd, indent=2, separators=(', ', ': '))
                                    await pkmn_class.Pokedex.generate_lists(self.bot)
                                    self.bot.raid_dict = await utils.get_raid_dict(self.bot)
                                    self.bot.raid_list = list(itertools.chain.from_iterable(self.bot.raid_dict.values()))
                                    for guild in list(self.bot.guilds):
                                        for report_dict in self.bot.channel_report_dicts:
                                            for channel_id in list(self.bot.guild_dict[guild.id].setdefault(report_dict, {}).keys()):
                                                if self.bot.guild_dict[guild.id][report_dict][channel_id]['egg_level'] == str(channel_level):
                                                    for trainer_id in list(self.bot.guild_dict[guild.id][report_dict][channel_id]['trainer_dict'].keys()):
                                                        interest = copy.copy(self.bot.guild_dict[guild.id][report_dict][channel_id]['trainer_dict'][trainer_id].get('interest', []))
                                                        new_bosses = list(set(new_raid_dict[channel_level]) - set(old_raid_dict[channel_level]))
                                                        new_bosses = [x.lower() for x in new_bosses]
                                                        self.bot.guild_dict[guild.id][report_dict][channel_id]['trainer_dict'][trainer_id]['interest'] = [*interest, *new_bosses]
                                                    self.bot.guild_dict[guild.id][report_dict][channel_id]['pokemon'] = ''
                                                    self.bot.guild_dict[guild.id][report_dict][channel_id]['ctrs_dict'] = {}
                                                    self.bot.guild_dict[guild.id][report_dict][channel_id]['ctrsmessage'] = None
                                                    channel = self.bot.get_channel(channel_id)
                                                    await raid_cog._edit_party(channel)
                            await raid_cog._eggtoraid(report_details.get('pokemon', None), channel, message.author, moveset=report_details.get('moves', None))
                            await asyncio.sleep(10)
                            if self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][channelid].get('type') == "egg":
                                await raid_cog._eggtoraid(report_details.get('pokemon', None), channel, message.author, moveset=report_details.get('moves', None))
                        raidexp = report_details.get('raidexp')
                        if raidexp and channel:
                            await raid_cog._timerset(channel, raidexp)
                        await raid_cog.set_moveset(ctx, channel, report_details.get('moves', None))
                        return
                if report_details.get('type', None) == "raid":
                    if not self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('scanners', {}).get('reports', {}).get('raid'):
                        return
                    reporttype = "raid"
                    pokemon = report_details.setdefault('pokemon', None)
                    pkmn_obj = report_details.setdefault('pkmn_obj', pokemon)
                    pkmn_obj = await pkmn_class.Pokemon.async_get_pokemon(self.bot, pkmn_obj)
                    if str(pkmn_obj) in ctx.bot.guild_dict[ctx.guild.id]['configure_dict'].get('scanners', {}).get('filters', {}).get('raid', []) or pkmn_obj.id in ctx.bot.guild_dict[ctx.guild.id]['configure_dict'].get('scanners', {}).get('filters', {}).get('raid', []):
                        return
                    if not utils.get_level(self.bot, pokemon):
                        return logger.error(f"{pokemon} not in raid_json")
                    coordinates = report_details.setdefault('gps', None)
                    raid_coordinates = report_details.setdefault('coordinates', coordinates)
                    raid_details = report_details.setdefault('gym', None)
                    if not all([pokemon, coordinates, raid_details]):
                        return
                    egg_level = "0"
                    timeout = int(report_details.get('raidexp', 45))*60
                    expiremsg = _('**This {pokemon} raid has expired!**').format(pokemon=pokemon.title())
                    egg_level = utils.get_level(self.bot, pokemon)
                    if egg_level.isdigit() and int(egg_level) in self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('scanners', {}).get('raidlvls', []):
                        auto_report = True
                    elif egg_level == "EX" and "EX" in self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('scanners', {}).get('raidlvls', []):
                        auto_report = True
                    else:
                        auto_report = False
                    if not raidhour:
                        if auto_report:
                            raid_channel = await self.huntr_raid(ctx, report_details)
                            if embed and raid_channel:
                                return await raid_channel.send(embed=embed)
                        else:
                            pokemon = await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, pokemon)
                            if not pokemon:
                                return
                            raidmsg = f"Meowth! {str(pokemon)} raid reported by {message.author.mention}! Details: {raid_details}. React if you want to make a channel for this raid! Use {report_emoji} to report new, or {list_emoji} to list unreported raids!"
                            ctx.raidreport = await ctx.channel.send(raidmsg, embed=embed)
                            dm_dict = await raid_cog.send_dm_messages(ctx, str(pokemon), raid_details, f"Meowth! {str(pokemon)} raid reported by {ctx.author.display_name} in {ctx.channel.mention}! Details: {raid_details}. React in {ctx.channel.mention} to report this raid!", copy.deepcopy(embed), dm_dict)
                    else:
                        raidmsg = ""
                        ctx.raidreport = ctx.message
                elif report_details.get('type', None) == "egg":
                    if not self.bot.guild_dict[message.guild.id]['configure_dict'].get('scanners', {}).get('reports', {}).get('egg'):
                        return
                    reporttype = "egg"
                    egg_level = report_details.setdefault('level', None)
                    egg_level = report_details.setdefault('egg_level', egg_level)
                    if egg_level in ctx.bot.guild_dict[message.guild.id]['configure_dict'].get('scanners', {}).get('filters', {}).get('egg', []):
                        return
                    coordinates = report_details.setdefault('gps', None)
                    raid_details = report_details.setdefault('gym', None)
                    if not all([egg_level, coordinates, raid_details]):
                        return
                    moves = None
                    pokemon = None
                    egg_level = str(egg_level)
                    timeout = int(report_details.get('raidexp', 45))*60
                    expiremsg = ('This level {level} raid egg has hatched!').format(level=egg_level)
                    if not raidhour:
                        if int(egg_level) in self.bot.guild_dict[message.guild.id]['configure_dict'].get('scanners', {}).get('egglvls', False):
                            raid_channel = await self.huntr_raidegg(ctx, report_details)
                            if embed and raid_channel:
                                return await raid_channel.send(embed=embed)
                        else:
                            raidmsg = f"Meowth! Level {egg_level} raid egg reported by {message.author.mention}! Details: {raid_details}. React if you want to make a channel for this raid! Use {report_emoji} to report new, or {list_emoji} to list unreported raids!"
                            ctx.raidreport = await ctx.channel.send(raidmsg, embed=embed)
                            dm_dict = await raid_cog.send_dm_messages(ctx, str(egg_level), raid_details, f"Meowth! Level {egg_level} raid egg reported by {ctx.author.display_name} in {ctx.channel.mention}! Details: {raid_details}. React in {ctx.channel.mention} to report this raid!", copy.deepcopy(embed), dm_dict)
                    else:
                        raidmsg = ""
                        ctx.raidreport = ctx.message
                self.bot.guild_dict[ctx.guild.id]['pokealarm_dict'][ctx.raidreport.id] = {
                    "exp":time.time() + timeout,
                    'expedit': {"content":raidmsg.split("React")[0], "embedcontent":expiremsg},
                    "reporttype":reporttype,
                    "report_channel":ctx.channel.id,
                    "level":egg_level,
                    "egg_level":egg_level,
                    "pokemon":str(pokemon) if pokemon else None,
                    "pkmn_obj":str(pokemon) if pokemon else None,
                    "gps":coordinates,
                    "coordinates":coordinates,
                    "gym":raid_details,
                    "raidexp":report_details.setdefault('raidexp', 45),
                    "reporttime":now,
                    "moves":report_details.setdefault('moves', None),
                    "embed":embed,
                    "dm_dict":dm_dict
                }
                if raidhour:
                    return
                await asyncio.sleep(0.25)
                for reaction in react_list:
                    await utils.add_reaction(ctx.raidreport, reaction)
                return
            elif report_details.get('type', None) == "wild":
                if not self.bot.guild_dict[message.guild.id]['configure_dict'].get('scanners', {}).get('reports', {}).get('wild'):
                    return
                wild_cog = self.bot.cogs.get('Wild')
                if not wild_cog:
                    logger.error("Wild Cog not loaded")
                    return
                reporttype = "wild"
                pokemon = report_details.setdefault('pokemon', None)
                coordinates = report_details.setdefault("gps", None)
                if not coordinates:
                    coordinates = report_details.setdefault("coordinates", None)
                    report_details['gps'] = coordinates
                report_details['coordinates'] = coordinates
                if not all([pokemon, coordinates]):
                    return
                return await self.huntr_wild(ctx, report_details)
            elif report_details.get('type', None) == "research":
                if not self.bot.guild_dict[message.guild.id]['configure_dict'].get('scanners', {}).get('reports', {}).get('research'):
                    return
                research_cog = self.bot.cogs.get('Research')
                if not research_cog:
                    logger.error("Research Cog not loaded")
                    return
                reporttype = "quest"
                pokestop = report_details.get('pokestop', None)
                coordinates = report_details.get('gps', None)
                quest = report_details.get('quest', None)
                reward = report_details.get('reward', None)
                pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, reward)
                reward_list = ["ball", "nanab", "pinap", "razz", "berr", "stardust", "potion", "revive", "candy", "lure", "module", "mysterious", "component", "radar", "sinnoh", "unova", "stone", "scale", "coat", "grade"]
                other_reward = any(x in reward.lower() for x in reward_list)
                if pokemon and not other_reward:
                    if str(pokemon) in ctx.bot.guild_dict[message.guild.id]['configure_dict'].get('scanners', {}).get('filters', {}).get('research', []) or pokemon.id in ctx.bot.guild_dict[message.guild.id]['configure_dict'].get('scanners', {}).get('filters', {}).get('research', []):
                        return
                else:
                    __, item_name = await utils.get_item(reward)
                    if item_name in ctx.bot.guild_dict[message.guild.id]['configure_dict'].get('scanners', {}).get('filters', {}).get('research', []):
                        return
                if not all([pokestop, coordinates, quest, reward]):
                    return
                return await self.huntr_research(ctx, report_details)
            elif report_details.get('type', None) == "lure":
                if not self.bot.guild_dict[message.guild.id]['configure_dict'].get('scanners', {}).get('reports', {}).get('lure'):
                    return
                lure_cog = self.bot.cogs.get('Lure')
                if not lure_cog:
                    logger.error("Lure Cog not loaded")
                    return
                reporttype = "lure"
                pokestop = report_details.get('pokestop', None)
                coordinates = report_details.get('gps', None)
                lure_type = report_details.get('lure_type', None)
                if lure_type in ctx.bot.guild_dict[message.guild.id]['configure_dict'].get('scanners', {}).get('filters', {}).get('lure', []):
                    return
                if not all([pokestop, coordinates, lure_type]):
                    return
                return await self.huntr_lure(ctx, report_details)
            elif report_details.get('type', None) == "invasion":
                if not self.bot.guild_dict[message.guild.id]['configure_dict'].get('scanners', {}).get('reports', {}).get('invasion'):
                    return
                invasion_cog = self.bot.cogs.get('Invasion')
                if not invasion_cog:
                    logger.error("Invasion Cog not loaded")
                    return
                reporttype = "invasion"
                pokestop = report_details.get('pokestop', None)
                coordinates = report_details.get('gps', None)
                reward = report_details.get('reward', None)
                if reward in ctx.bot.guild_dict[message.guild.id]['configure_dict'].get('scanners', {}).get('filters', {}).get('invasion', []):
                    return
                if not all([pokestop, coordinates]):
                    return
                return await self.huntr_invasion(ctx, report_details)
        else:
            await utils.safe_delete(message)
            pokealarm_dict = copy.deepcopy(self.bot.guild_dict[message.guild.id].get('pokealarm_dict', {}))
            report_details = pokealarm_dict[message.id]
            embed = report_details['embed']
            reporttime = report_details['reporttime']
            reporttype = report_details['reporttype']
            huntrtime = report_details['raidexp']
            dm_dict = copy.deepcopy(report_details['dm_dict'])
            reacttime = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
            timediff = relativedelta(reacttime, reporttime)
            exptime = int(huntrtime) - int(timediff.minutes)
            report_details['raidexp'] = exptime
            if reporttype == "egg":
                raid_channel = await self.huntr_raidegg(ctx, report_details, report_user=reactuser, dm_dict=dm_dict)
            elif reporttype == "raid":
                raid_channel = await self.huntr_raid(ctx, report_details, report_user=reactuser, dm_dict=dm_dict)
            if embed and raid_channel:
                await raid_channel.send(embed=embed)
            if raid_channel:
                return raid_channel

    """Reporting"""

    async def huntr_wild(self, ctx, report_details, reporter=None, report_user=None, dm_dict=None):
        if not dm_dict:
            dm_dict = {}
        if report_user:
            ctx.message.author = report_user
        message = ctx.message
        gender = report_details.setdefault("gender", None)
        wild_details = report_details['coordinates']
        level = str(report_details.get("level", ''))
        cp = str(report_details.get("cp", ''))
        weather = report_details.get("weather", '')
        if "ditto" in report_details['pokemon'].lower():
            pokemon = await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, f"{gender if gender else ''} Ditto")
            disguise = await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, f"{gender if gender else ''} {report_details['pokemon'].lower().replace('ditto', '')}")
            report_details['disguise'] = str(disguise)
        else:
            pokemon = await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, f"{gender if gender else ''} {report_details['pokemon']}")
            disguise = None
        if pokemon:
            entered_wild = pokemon.name.lower()
            pokemon.shiny = False
            pokemon.level = level
            pokemon.cp = cp
        else:
            return
        if "rain" in weather:
            pokemon.weather = "rainy"
        elif "partly" in weather:
            pokemon.weather = "partlycloudy"
        elif "clear" in weather:
            pokemon.weather = "clear"
        elif "cloudy" in weather:
            pokemon.weather = "cloudy"
        elif "wind" in weather:
            pokemon.weather = "windy"
        elif "snow" in weather:
            pokemon.weather = "snowy"
        elif "fog" in weather:
            pokemon.weather = "foggy"
        report_details['weather'] = pokemon.weather
        if pokemon.id in ctx.bot.guild_dict[ctx.channel.guild.id]['configure_dict'].get('scanners', {}).setdefault('filters', {}).setdefault('wild', []) or str(pokemon) in ctx.bot.guild_dict[ctx.channel.guild.id]['configure_dict'].get('scanners', {}).setdefault('filters', {}).setdefault('wild', []):
            if not report_details.get("iv_percent", '') and not report_details.get("level", ''):
                if weather:
                    ctx.bot.guild_dict[message.guild.id]['wildreport_dict'][ctx.message.id] = {
                        'report_time':time.time(),
                        'exp':time.time() + 60*(60-datetime.datetime.utcnow().minute),
                        'coordinates':wild_details,
                        'pkmn_obj':str(pokemon),
                        'weather':pokemon.weather,
                        'filtered': True
                    }
                return
        wild_iv = {}
        iv_percent = report_details.get("iv_percent", '')
        iv_long = report_details.get("iv_long", 'X / X / X')
        iv_atk = iv_long.split('/')[0].strip()
        iv_def = iv_long.split('/')[1].strip()
        iv_sta = iv_long.split('/')[2].strip()
        if iv_percent:
            if utils.is_number(iv_percent) and float(iv_percent) >= 0 and float(iv_percent) <= 100:
                iv_percent = int(round(float(iv_percent)))
            else:
                iv_percent = None
        report_details['wild_iv'] = {'percent':iv_percent, 'iv_atk':iv_atk, 'iv_def':iv_def, 'iv_sta':iv_sta}
        wild_iv = {'percent':iv_percent, 'iv_atk':iv_atk, 'iv_def':iv_def, 'iv_sta':iv_sta}
        pokemon.iv = wild_iv
        if iv_percent or iv_percent == 0:
            iv_str = f" | **{iv_percent}IV**"
        else:
            iv_str = ""
        height = report_details.get("height", '')
        weight = report_details.get("weight", '')
        height = re.sub('[^0-9 .]', '', height)
        weight = re.sub('[^0-9 .]', '', weight)
        size = None
        if height and weight and pokemon.weight and pokemon.height:
            weight_ratio = float(weight) / float(pokemon.weight)
            height_ratio = float(height) / float(pokemon.height)
            if height_ratio + weight_ratio < 1.5:
                size = "XS"
            elif height_ratio + weight_ratio > 2.5:
                size = "XL"
        pokemon.size = size if pokemon.size_available else None
        moveset = report_details.get("moveset", '')
        expire = report_details.setdefault("expire", "45 min 00 sec")
        nearest_stop = str(wild_details)
        nearest_poi = ""
        poi_info = ""
        wild_cog = self.bot.get_cog("Wild")
        expiremsg = _('**This {pokemon} has despawned!**').format(pokemon=entered_wild.title())
        if reporter == "huntr":
            huntr_url = wild_details
            wild_coordinates = wild_details.split("#")[1]
        else:
            wild_coordinates = wild_details
        wild_gmaps_link = f"https://www.google.com/maps/search/?api=1&query={wild_coordinates}"
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        if gym_matching_cog:
            nearest_poi = await gym_matching_cog.find_nearest_poi(wild_coordinates, ctx.guild.id)
            nearest_stop = await gym_matching_cog.find_nearest_stop(wild_coordinates, ctx.guild.id)
            if nearest_poi:
                wild_details = nearest_poi
                poi_info, __, __ = await gym_matching_cog.get_poi_info(ctx, wild_details.strip(), "wild")
        if nearest_stop:
            report_details['location'] = nearest_stop
        else:
            report_details['location'] = str(wild_details)
        report_details['pkmn_obj'] = str(pokemon)
        stop_str = ""
        if nearest_stop or nearest_poi:
            stop_str = f"{' Details: '+nearest_poi+' |' if nearest_poi and nearest_poi != nearest_stop else ''}{' Nearest Pokestop: '+nearest_stop if nearest_stop else ''}{' | ' if nearest_poi or nearest_stop else ' '}"
        wild_embed = await wild_cog.make_wild_embed(ctx, report_details)
        omw_emoji = ctx.bot.custom_emoji.get('wild_omw', u'\U0001F3CE\U0000fe0f')
        expire_emoji = ctx.bot.custom_emoji.get('wild_despawn', u'\U0001F4A8')
        info_emoji = ctx.bot.custom_emoji.get('wild_info', u'\U00002139\U0000fe0f')
        catch_emoji = ctx.bot.custom_emoji.get('wild_catch', u'\U000026be')
        report_emoji = self.bot.custom_emoji.get('wild_report', u'\U0001F4E2')
        list_emoji = ctx.bot.custom_emoji.get('list_emoji', u'\U0001f5d2\U0000fe0f')
        reaction_list = [omw_emoji, catch_emoji, expire_emoji, info_emoji, report_emoji, list_emoji]
        despawn = (int(expire.split(' ')[0]) * 60) + int(expire.split(' ')[2])
        ctx.wildreportmsg = await ctx.channel.send(f"Meowth! Wild {str(pokemon)} reported by {message.author.mention}!{stop_str}Coordinates: {wild_coordinates}{iv_str}\n\nUse {omw_emoji} if coming, {catch_emoji} if caught, {expire_emoji} if despawned, {info_emoji} to edit details, {report_emoji} to report new, or {list_emoji} to list all wilds!", embed=wild_embed)
        ctx.bot.guild_dict[ctx.guild.id]['wildreport_dict'][ctx.wildreportmsg.id] = {
            'report_time':time.time(),
            'exp':time.time() + despawn,
            'expedit': {"content":ctx.wildreportmsg.content, "embedcontent":expiremsg},
            'report_message':message.id,
            'report_channel':ctx.channel.id,
            'report_author':ctx.author.id,
            'report_guild':ctx.guild.id,
            'dm_dict':{},
            'location':wild_details,
            'coordinates':wild_coordinates,
            'url':wild_gmaps_link,
            'pokemon':entered_wild,
            'pkmn_obj':str(pokemon),
            'wild_iv':wild_iv,
            'level':level,
            'cp':cp,
            'gender':gender,
            'size':size,
            'weather':pokemon.weather,
            'omw':[]
        }
        self.bot.active_wilds[ctx.wildreportmsg.id] = pokemon
        if disguise:
            ctx.bot.guild_dict[ctx.guild.id]['wildreport_dict'][ctx.wildreportmsg.id]['disguise'] = str(disguise)
        for wildid in ctx.bot.guild_dict[ctx.guild.id]['wildreport_dict']:
            report_time = ctx.bot.guild_dict[ctx.guild.id]['wildreport_dict'][ctx.wildreportmsg.id].get('report_time', time.time())
            dupe_channel = ctx.bot.guild_dict[ctx.guild.id]['wildreport_dict'][ctx.wildreportmsg.id].get('report_channel', ctx.channel.id)
            dupe_time = ctx.bot.guild_dict[ctx.guild.id]['wildreport_dict'][wildid].get('report_time', time.time())
            dupe_coord = ctx.bot.guild_dict[ctx.guild.id]['wildreport_dict'][wildid].get('coordinates', None)
            dupe_pokemon = ctx.bot.guild_dict[ctx.guild.id]['wildreport_dict'][wildid].get('pkmn_obj', None)
            dupe_iv = ctx.bot.guild_dict[ctx.guild.id]['wildreport_dict'][wildid].get('wild_iv', {})
            dupe_level = ctx.bot.guild_dict[ctx.guild.id]['wildreport_dict'][wildid].get('level', 0)
            dupe_cp = ctx.bot.guild_dict[ctx.guild.id]['wildreport_dict'][wildid].get('cp', 0)
            report_filter = ctx.bot.guild_dict[ctx.guild.id]['wildreport_dict'][wildid].get('filtered', False)
            if report_filter:
                continue
            if dupe_time < report_time and dupe_channel == ctx.channel.id and dupe_coord == wild_coordinates and dupe_pokemon == str(pokemon) and dupe_iv == wild_iv and dupe_level == level and dupe_cp == cp:
                ctx.bot.guild_dict[ctx.guild.id]['wildreport_dict'][ctx.wildreportmsg.id]['expedit']['embedcontent'] = f"**This {str(pokemon)} was a duplicate!**"
                return await wild_cog.expire_wild(ctx.wildreportmsg)
            elif dupe_channel == ctx.channel.id and dupe_coord == wild_coordinates and dupe_pokemon == str(pokemon) and not wild_iv.get('percent') and dupe_iv.get('percent'):
                ctx.bot.guild_dict[ctx.guild.id]['wildreport_dict'][ctx.wildreportmsg.id]['expedit']['embedcontent'] = f"**This {str(pokemon)} was a duplicate!**"
                return await wild_cog.expire_wild(ctx.wildreportmsg)
            elif dupe_channel == ctx.channel.id and dupe_coord == wild_coordinates and dupe_pokemon == str(pokemon) and wild_iv.get('percent') and not dupe_iv.get('percent'):
                ctx.bot.guild_dict[ctx.guild.id]['wildreport_dict'][wildid]['exp'] = ctx.bot.guild_dict[ctx.guild.id]['wildreport_dict'][ctx.wildreportmsg.id]['exp']
                ctx.bot.guild_dict[ctx.guild.id]['wildreport_dict'][wildid]['wild_iv'] = ctx.bot.guild_dict[ctx.guild.id]['wildreport_dict'][ctx.wildreportmsg.id]['wild_iv']
                ctx.bot.guild_dict[ctx.guild.id]['wildreport_dict'][wildid]['level'] = ctx.bot.guild_dict[ctx.guild.id]['wildreport_dict'][ctx.wildreportmsg.id]['level']
                ctx.bot.guild_dict[ctx.guild.id]['wildreport_dict'][wildid]['cp'] = ctx.bot.guild_dict[ctx.guild.id]['wildreport_dict'][ctx.wildreportmsg.id]['cp']
                ctx.bot.guild_dict[ctx.guild.id]['wildreport_dict'][wildid]['gender'] = ctx.bot.guild_dict[ctx.guild.id]['wildreport_dict'][ctx.wildreportmsg.id]['gender']
                ctx.bot.guild_dict[ctx.guild.id]['wildreport_dict'][wildid]['size'] = ctx.bot.guild_dict[ctx.guild.id]['wildreport_dict'][ctx.wildreportmsg.id]['size']
                ctx.bot.guild_dict[ctx.guild.id]['wildreport_dict'][ctx.wildreportmsg.id]['expedit']['embedcontent'] = f"**This {str(pokemon)} was a duplicate!**"
                await wild_cog.expire_wild(ctx.wildreportmsg)
                dupe_message = await ctx.channel.fetch_message(wildid)
                return await wild_cog.edit_wild_messages(ctx, dupe_message)
        dm_dict = await wild_cog.send_dm_messages(ctx, str(pokemon), str(nearest_stop), wild_iv, level, cp, ctx.wildreportmsg.content.replace(ctx.author.mention, f"{ctx.author.display_name} in {ctx.channel.mention}"), wild_embed.copy(), dm_dict)
        ctx.bot.guild_dict[ctx.guild.id]['wildreport_dict'][ctx.wildreportmsg.id]['dm_dict'] = dm_dict
        for reaction in reaction_list:
            await asyncio.sleep(0.25)
            await utils.add_reaction(ctx.wildreportmsg, reaction)

    async def huntr_raid(self, ctx, report_details, reporter=None, report_user=None, dm_dict=None):
        if not dm_dict:
            dm_dict = {}
        raid_cog = self.bot.cogs.get('Raid')
        bot_account = ctx.author
        if report_user:
            ctx.author, ctx.message.author = report_user, report_user
        message = ctx.message
        help_reaction = self.bot.custom_emoji.get('raid_info', u'\U00002139\U0000fe0f')
        maybe_reaction = self.bot.custom_emoji.get('raid_maybe', u'\U00002753')
        omw_reaction = self.bot.custom_emoji.get('raid_omw', u'\U0001f3ce\U0000fe0f')
        here_reaction = self.bot.custom_emoji.get('raid_here', u'\U0001F4CD')
        cancel_reaction = self.bot.custom_emoji.get('raid_cancel', u'\U0000274C')
        report_emoji = self.bot.custom_emoji.get('raid_report', u'\U0001F4E2')
        list_emoji = ctx.bot.custom_emoji.get('list_emoji', u'\U0001f5d2\U0000fe0f')
        react_list = [maybe_reaction, omw_reaction, here_reaction, cancel_reaction]
        timestamp = (message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[ctx.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))).strftime(_('%I:%M %p (%H:%M)'))
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
        entered_raid = report_details['pokemon']
        raid_coordinates = report_details['gps']
        report_details['coordinates'] = raid_coordinates
        raid_details = report_details.get('gym', raid_coordinates)
        report_details['address'] = raid_details
        moves = report_details.get('moves', None)
        raidexp = report_details.get('raidexp', 45)
        pokemon = await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, entered_raid)
        if pokemon:
            pokemon.shiny = False
            pokemon.gender = False
            pokemon.size = None
            pokemon.shadow = None
        else:
            return
        if not pokemon.id in ctx.bot.raid_list:
            await ctx.channel.send(_('Meowth! The Pokemon {pokemon} does not appear in raids!').format(pokemon=pokemon.name.capitalize()), delete_after=10)
            return
        elif utils.get_level(ctx.bot, str(pokemon)) == "EX":
            await ctx.channel.send(_("Meowth! The Pokemon {pokemon} only appears in EX Raids! Use **!exraid** to report one!").format(pokemon=pokemon.name.capitalize()), delete_after=10)
            return
        level = utils.get_level(ctx.bot, str(pokemon))
        matched_boss = False
        for boss in self.bot.raid_dict[str(level)]:
            if isinstance(boss, pkmn_class.Pokemon) and str(boss) == str(pokemon):
                pokemon = copy.copy(boss)
                matched_boss = True
                break
        if not matched_boss:
            for boss in self.bot.raid_dict[str(level)]:
                if isinstance(boss, pkmn_class.Pokemon) and boss and boss.id == pokemon.id:
                    pokemon = copy.copy(boss)
                    break
        weather = ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'].get(ctx.channel.id, {}).get('weather', None)
        if not weather and raid_coordinates:
            weather = await raid_cog.auto_weather(ctx, raid_coordinates)
        report_details['pkmn_obj'] = str(pokemon)
        report_details['weather'] = weather
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        if gym_matching_cog:
            gym_info, raid_location, gym_url = await gym_matching_cog.get_poi_info(ctx, raid_details, "raid", dupe_check=False, autocorrect=False)
            if gym_url:
                raid_details = raid_location
            elif raid_details.lower() != "unknown" and raid_coordinates not in str(gym_matching_cog.get_gyms(ctx.guild.id)):
                pokestops = gym_matching_cog.get_stops(ctx.guild.id)
                if raid_location in list(pokestops.keys()):
                    with open(os.path.join('data', 'stop_data.json'), 'r') as fd:
                        data = json.load(fd)
                    convert_dict = {}
                    poi_data_coords = data[str(ctx.guild.id)].get(raid_details, {}).get('coordinates', "")
                    poi_data_alias = data[str(ctx.guild.id)].get(raid_details, {}).get('alias', "")
                    poi_data_notes = data[str(ctx.guild.id)].get(raid_details, {}).get('notes', "")
                    convert_dict[raid_details] = {"coordinates": poi_data_coords, "alias": poi_data_alias, "notes": poi_data_alias}
                    del data[str(ctx.guild.id)][raid_details]
                    for k in list(data[str(ctx.guild.id)].keys()):
                        if data[str(ctx.guild.id)][k].get('alias', None) == raid_details:
                            convert_dict[k] = {"coordinates": data[str(ctx.guild.id)][k].get('coordinates'), "alias": data[str(ctx.guild.id)][k].get('alias', ""), "notes":data[str(ctx.guild.id)][k].get('notes', "")}
                            del data[str(ctx.guild.id)][k]
                    with open(os.path.join('data', 'stop_data.json'), 'w') as fd:
                        json.dump(data, fd, indent=2, separators=(', ', ': '))
                    with open(os.path.join('data', 'gym_data.json'), 'r') as fd:
                        data = json.load(fd)
                    data[str(ctx.guild.id)] = {**data[str(ctx.guild.id)], **convert_dict}
                    with open(os.path.join('data', 'gym_data.json'), 'w') as fd:
                        json.dump(data, fd, indent=2, separators=(', ', ': '))
                else:
                    try:
                        with open(os.path.join('data', 'gym_data.json'), 'r') as fd:
                            data = json.load(fd)
                    except:
                        data = {}
                    add_gym_dict = {}
                    add_gym_dict[raid_details] = {"coordinates":raid_coordinates, "alias":"", "notes":""}
                    data[str(ctx.guild.id)] = {**data.get(str(ctx.guild.id), {}), **add_gym_dict}
                    with open(os.path.join('data', 'gym_data.json'), 'w') as fd:
                        json.dump(data, fd, indent=2, separators=(', ', ': '))
                gym_matching_cog.gym_data = gym_matching_cog.init_json()
                gym_matching_cog.stop_data = gym_matching_cog.init_stop_json()
            elif raid_coordinates in str(gym_matching_cog.get_gyms(ctx.guild.id)):
                test_gym = await gym_matching_cog.find_nearest_gym(raid_coordinates, ctx.guild.id)
                gym_info, raid_location, gym_url = await gym_matching_cog.get_poi_info(ctx, test_gym, "raid", dupe_check=False, autocorrect=False)
                if gym_url:
                    raid_details = raid_location
        raid_embed = await raid_cog.make_raid_embed(ctx, report_details, raidexp)
        if not raid_embed:
            return
        raid_channel = await raid_cog.create_raid_channel(ctx, f"{boss.name.lower()}{'-'+boss.region.lower() if boss.region else ''}{'-'+boss.form.lower() if boss.form else ''}", raid_details, "raid")
        if not raid_channel:
            return
        await asyncio.sleep(1)
        ctx.raidreport = await ctx.channel.send(content=f"Meowth! {str(pokemon).title()} raid reported by {message.author.mention}! Details: {raid_details}. Coordinate in {raid_channel.mention}\n\nUse {maybe_reaction} if interested, {omw_reaction} if coming, {here_reaction} if there, {cancel_reaction} to cancel, {report_emoji} to report new, or {list_emoji} to list all raids!", embed=raid_embed)
        raidmsg = f"Meowth! {str(pokemon).title()} raid reported by {message.author.mention} in {ctx.channel.mention}! Details: {raid_details}. Coordinate here!\n\nClick the {help_reaction} to get help on commands, {maybe_reaction} if interested, {omw_reaction} if coming, {here_reaction} if there, or {cancel_reaction} to cancel.\n\nThis channel will be deleted five minutes after the timer expires."
        raid_message = await raid_channel.send(content=raidmsg, embed=raid_embed)
        await utils.add_reaction(raid_message, help_reaction)
        for reaction in react_list:
            await asyncio.sleep(0.25)
            await utils.add_reaction(raid_message, reaction)
            await asyncio.sleep(0.25)
            await utils.add_reaction(ctx.raidreport, reaction)
        await utils.add_reaction(ctx.raidreport, report_emoji)
        await utils.add_reaction(ctx.raidreport, list_emoji)
        await raid_message.pin()
        level = utils.get_level(self.bot, str(pokemon))
        if raidexp > ctx.bot.raid_info['raid_eggs'][level]['raidtime']:
            with open(os.path.join('data', 'raid_info.json'), 'r') as fd:
                data = json.load(fd)
            data['raid_eggs'][level]['raidtime'] = int(raidexp)
            with open(os.path.join('data', 'raid_info.json'), 'w') as fd:
                json.dump(data, fd, indent=2, separators=(', ', ': '))
        ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid_channel.id] = {
            'report_channel':ctx.channel.id,
            'report_guild':ctx.guild.id,
            'report_author':ctx.author.id,
            'trainer_dict': {},
            'report_time':time.time(),
            'exp': time.time() + (60 * ctx.bot.raid_info['raid_eggs'][str(level)]['raidtime']),
            'manual_timer': False,
            'active': True,
            'raid_message':raid_message.id,
            'raid_report':ctx.raidreport.id,
            'raid_embed':raid_embed,
            'report_message':message.id,
            'address': raid_details,
            'location':raid_details,
            'type': 'raid',
            'pokemon': pokemon.name.lower(),
            'pkmn_obj': str(pokemon),
            'egg_level': '0',
            'moveset': 0,
            'weather': weather,
            'coordinates':raid_coordinates,
            'dm_dict':dm_dict
        }
        await raid_cog._timerset(raid_channel, raidexp)
        if not ctx.prefix:
            prefix = self.bot._get_prefix(self.bot, ctx.message)
            ctx.prefix = prefix[-1]
        if bot_account.bot:
            duplicate_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url=bot_account.avatar_url)
            duplicate_embed.add_field(name=f"**Bot Reported Channel**", value=f"This raid was reported by a bot ({bot_account.mention}). If it is a duplicate of a channel already reported by a human, I can remove it with three **{ctx.prefix}duplicate** messages.")
            duplicate_msg = await raid_channel.send(embed=duplicate_embed, delete_after=1800)
        weather_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/weatherIcon_large_extreme.png?cache=1")
        weather_embed.add_field(name=f"**Channel Weather**", value=f"The weather is currently set to {str(weather).replace('partlycloudy', 'partly cloudy')}. This may be innaccurate. You can set the correct weather using **{ctx.prefix}weather**.{'**Boosted**: ' + ('').join([utils.type_to_emoji(self.bot, x) for x in utils.get_weather_boost(str(weather))]) if weather else ''}\n\n{str(pokemon)+' is ***boosted*** in '+str(weather)+' weather.' if pokemon.is_boosted else ''}")
        if weather:
            weather_embed.set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/weatherIcon_large_{str(weather).lower()}{'Day' if now.hour >= 6 and now.hour <= 18 else 'Night'}.png?cache=1")
        weather_msg = await raid_channel.send(embed=weather_embed)
        ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid_channel.id]['weather_msg'] = weather_msg.id
        ctrs_dict = await raid_cog._get_generic_counters(raid_channel, str(pokemon), weather)
        if str(level) in ctx.bot.guild_dict[message.guild.id]['configure_dict'].get('counters', {}).get('auto_levels', []):
            try:
                ctrsmsg = f"Here are the best counters for **{str(pokemon)}**! React below to change the moveset."
                ctrsmessage = await raid_channel.send(content=ctrsmsg, embed=ctrs_dict[0]['embed'])
                ctrsmessage_id = ctrsmessage.id
                await ctrsmessage.pin()
                for moveset in ctrs_dict:
                    await utils.add_reaction(ctrsmessage, ctrs_dict[moveset]['emoji'])
                    await asyncio.sleep(0.25)
            except:
                ctrsmessage_id = None
        else:
            ctrsmessage_id = None
        ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid_channel.id]['ctrsmessage'] = ctrsmessage_id
        ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid_channel.id]['ctrs_dict'] = ctrs_dict
        self.event_loop.create_task(raid_cog.expiry_check(raid_channel))
        index = 0
        for field in raid_embed.fields:
            if "reaction" in field.name.lower() or "status" in field.name.lower() or "team" in field.name.lower():
                raid_embed.remove_field(index)
            else:
                index += 1
        ctx.raid_channel = raid_channel
        dm_dict = self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][raid_channel.id].get('dm_dict', {})
        dm_dict = await raid_cog.send_dm_messages(ctx, str(pokemon), raid_details, ctx.raidreport.content.replace(ctx.author.mention, f"{ctx.author.display_name} in {ctx.channel.mention}"), copy.deepcopy(raid_embed), dm_dict)
        self.bot.loop.create_task(raid_cog.edit_dm_messages(ctx, ctx.raidreport.content, copy.deepcopy(raid_embed), dm_dict))
        ctx.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][raid_channel.id]['dm_dict'] = dm_dict
        if report_user:
            raid_reports = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(report_user.id, {}).setdefault('reports', {}).setdefault('raid', 0) + 1
            self.bot.guild_dict[ctx.guild.id]['trainers'][report_user.id]['reports']['raid'] = raid_reports
        await raid_cog.set_moveset(ctx, raid_channel, moves)
        return raid_channel

    async def huntr_raidegg(self, ctx, report_details, reporter=None, report_user=None, dm_dict=None):
        if not dm_dict:
            dm_dict = {}
        raid_cog = self.bot.cogs.get('Raid')
        bot_account = ctx.author
        if report_user:
            ctx.author, ctx.message.author = report_user, report_user
        message = ctx.message
        help_reaction = self.bot.custom_emoji.get('raid_info', u'\U00002139\U0000fe0f')
        maybe_reaction = self.bot.custom_emoji.get('raid_maybe', u'\U00002753')
        omw_reaction = self.bot.custom_emoji.get('raid_omw', u'\U0001f3ce\U0000fe0f')
        here_reaction = self.bot.custom_emoji.get('raid_here', u'\U0001F4CD')
        cancel_reaction = self.bot.custom_emoji.get('raid_cancel', u'\U0000274C')
        report_emoji = self.bot.custom_emoji.get('raid_report', u'\U0001F4E2')
        list_emoji = ctx.bot.custom_emoji.get('list_emoji', u'\U0001f5d2\U0000fe0f')
        react_list = [maybe_reaction, omw_reaction, here_reaction, cancel_reaction]
        timestamp = (message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[ctx.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))).strftime(_('%I:%M %p (%H:%M)'))
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
        egg_level = str(report_details.get('level'))
        raid_details = report_details.get('gym')
        raidexp = report_details.get('raidexp', 60)
        raid_coordinates = report_details['gps']
        report_details['coordinates'] = raid_coordinates
        raid_details = report_details.get('gym', raid_coordinates)
        report_details['address'] = raid_details
        weather = ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'].get(ctx.channel.id, {}).get('weather', None)
        if not weather and raid_coordinates:
            weather = await raid_cog.auto_weather(ctx, raid_coordinates)
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        if gym_matching_cog:
            gym_info, raid_location, gym_url = await gym_matching_cog.get_poi_info(ctx, raid_details, "raid", dupe_check=False, autocorrect=False)
            if gym_url:
                raid_details = raid_location
            elif raid_details.lower() != "unknown" and raid_coordinates not in str(gym_matching_cog.get_gyms(ctx.guild.id)):
                pokestops = gym_matching_cog.get_stops(ctx.guild.id)
                if raid_location in list(pokestops.keys()):
                    with open(os.path.join('data', 'stop_data.json'), 'r') as fd:
                        data = json.load(fd)
                    convert_dict = {}
                    poi_data_coords = data[str(ctx.guild.id)].get(raid_details, {}).get('coordinates', "")
                    poi_data_alias = data[str(ctx.guild.id)].get(raid_details, {}).get('alias', "")
                    poi_data_notes = data[str(ctx.guild.id)].get(raid_details, {}).get('notes', "")
                    convert_dict[raid_details] = {"coordinates": poi_data_coords, "alias": poi_data_alias, "notes": poi_data_alias}
                    del data[str(ctx.guild.id)][raid_details]
                    for k in list(data[str(ctx.guild.id)].keys()):
                        if data[str(ctx.guild.id)][k].get('alias', None) == raid_details:
                            convert_dict[k] = {"coordinates": data[str(ctx.guild.id)][k].get('coordinates'), "alias": data[str(ctx.guild.id)][k].get('alias', ""), "notes":data[str(ctx.guild.id)][k].get('notes', "")}
                            del data[str(ctx.guild.id)][k]
                    with open(os.path.join('data', 'stop_data.json'), 'w') as fd:
                        json.dump(data, fd, indent=2, separators=(', ', ': '))
                    with open(os.path.join('data', 'gym_data.json'), 'r') as fd:
                        data = json.load(fd)
                    data[str(ctx.guild.id)] = {**data[str(ctx.guild.id)], **convert_dict}
                    with open(os.path.join('data', 'gym_data.json'), 'w') as fd:
                        json.dump(data, fd, indent=2, separators=(', ', ': '))
                else:
                    try:
                        with open(os.path.join('data', 'gym_data.json'), 'r') as fd:
                            data = json.load(fd)
                    except:
                        data = {}
                    add_gym_dict = {}
                    add_gym_dict[raid_details] = {"coordinates":raid_coordinates, "alias":"", "notes":""}
                    data[str(ctx.guild.id)] = {**data.get(str(ctx.guild.id), {}), **add_gym_dict}
                    with open(os.path.join('data', 'gym_data.json'), 'w') as fd:
                        json.dump(data, fd, indent=2, separators=(', ', ': '))
            elif raid_coordinates in str(gym_matching_cog.get_gyms(ctx.guild.id)):
                test_gym = await gym_matching_cog.find_nearest_gym(raid_coordinates, ctx.guild.id)
                gym_info, raid_location, gym_url = await gym_matching_cog.get_poi_info(ctx, test_gym, "raid", dupe_check=False, autocorrect=False)
                if gym_url:
                    raid_details = raid_location
        raid_embed = await raid_cog.make_raid_embed(ctx, report_details, raidexp)
        if not raid_embed:
            return
        raid_channel = await raid_cog.create_raid_channel(ctx, egg_level, raid_details, "egg")
        if not raid_channel:
            return
        await asyncio.sleep(1)
        ctx.raidreport = await ctx.channel.send(content=f"Meowth! Level {egg_level} raid egg reported by {message.author.mention}! Details: {raid_details}. Coordinate in {raid_channel.mention}\n\nUse {maybe_reaction} if interested, {omw_reaction} if coming, {here_reaction} if there, {cancel_reaction} to cancel, {report_emoji} to report new, or {list_emoji} to list all raids!", embed=raid_embed)
        raidmsg = f"Meowth! Level {egg_level} raid egg reported by {message.author.mention} in {ctx.channel.mention}! Details: {raid_details}. Coordinate here!\n\nClick the {help_reaction} to get help on commands, {maybe_reaction} if interested, {omw_reaction} if coming, {here_reaction} if there, or {cancel_reaction} to cancel.\n\nThis channel will be deleted five minutes after the timer expires."
        raid_message = await raid_channel.send(content=raidmsg, embed=raid_embed)
        await utils.add_reaction(raid_message, help_reaction)
        for reaction in react_list:
            await asyncio.sleep(0.25)
            await utils.add_reaction(raid_message, reaction)
            await asyncio.sleep(0.25)
            await utils.add_reaction(ctx.raidreport, reaction)
        await utils.add_reaction(ctx.raidreport, report_emoji)
        await utils.add_reaction(ctx.raidreport, list_emoji)
        await raid_message.pin()
        if raidexp > ctx.bot.raid_info['raid_eggs'][egg_level]['hatchtime']:
            with open(os.path.join('data', 'raid_info.json'), 'r') as fd:
                data = json.load(fd)
            data['raid_eggs'][egg_level]['hatchtime'] = int(raidexp)
            with open(os.path.join('data', 'raid_info.json'), 'w') as fd:
                json.dump(data, fd, indent=2, separators=(', ', ': '))
        ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid_channel.id] = {
            'report_channel':ctx.channel.id,
            'report_guild':ctx.guild.id,
            'report_author':ctx.author.id,
            'trainer_dict': {},
            'report_time':time.time(),
            'exp': time.time() + (60 * ctx.bot.raid_info['raid_eggs'][egg_level]['hatchtime']),
            'manual_timer': False,
            'active': True,
            'raid_message':raid_message.id,
            'raid_report': ctx.raidreport.id,
            'raid_report':ctx.raidreport.id,
            'raid_embed':raid_embed,
            'report_message':message.id,
            'address': raid_details,
            'type': 'egg',
            'pokemon': '',
            'egg_level':egg_level,
            'weather': weather,
            'moveset': 0,
            'coordinates':raid_coordinates,
            'dm_dict':dm_dict
        }
        if raidexp is not False:
            await raid_cog._timerset(raid_channel, raidexp)
        if bot_account.bot:
            duplicate_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url=bot_account.avatar_url)
            duplicate_embed.add_field(name=f"**Bot Reported Channel**", value=f"This raid was reported by a bot ({bot_account.mention}). If it is a duplicate of a channel already reported by a human, I can remove it with three **{ctx.prefix}duplicate** messages.")
            duplicate_msg = await raid_channel.send(embed=duplicate_embed, delete_after=1800)
        weather_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/weatherIcon_large_extreme.png?cache=1")
        weather_embed.add_field(name=f"**Channel Weather**", value=f"The weather is currently set to {str(weather).replace('partlycloudy', 'partly cloudy')}. This may be innaccurate. You can set the correct weather using **{ctx.prefix}weather**.\n\n{'**Boosted**: ' + ('').join([utils.type_to_emoji(self.bot, x) for x in utils.get_weather_boost(str(weather))]) if weather else ''}")
        if weather:
            weather_embed.set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/weatherIcon_large_{str(weather).lower()}{'Day' if now.hour >= 6 and now.hour <= 18 else 'Night'}.png?cache=1")
        weather_msg = await raid_channel.send(embed=weather_embed)
        ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid_channel.id]['weather_msg'] = weather_msg.id
        if len(ctx.bot.raid_info['raid_eggs'][egg_level]['pokemon']) == 1:
            await raid_cog._eggassume(ctx, str(ctx.bot.raid_info['raid_eggs'][egg_level]['pokemon'][0]), raid_channel)
        elif egg_level == "5" and ctx.bot.guild_dict[raid_channel.guild.id]['configure_dict'].get('settings', {}).get('regional', None) in ctx.bot.raid_list:
            await raid_cog._eggassume(ctx, str(ctx.bot.guild_dict[raid_channel.guild.id]['configure_dict']['settings']['regional']), raid_channel)
        self.event_loop.create_task(raid_cog.expiry_check(raid_channel))
        index = 0
        for field in raid_embed.fields:
            if "reaction" in field.name.lower() or "status" in field.name.lower() or "team" in field.name.lower():
                raid_embed.remove_field(index)
            else:
                index += 1
        ctx.raid_channel = raid_channel
        dm_dict = self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][raid_channel.id].get('dm_dict', {})
        dm_dict = await raid_cog.send_dm_messages(ctx, str(egg_level), raid_details, ctx.raidreport.content.replace(ctx.author.mention, f"{ctx.author.display_name} in {ctx.channel.mention}"), copy.deepcopy(raid_embed), dm_dict)
        self.bot.loop.create_task(raid_cog.edit_dm_messages(ctx, ctx.raidreport.content, copy.deepcopy(raid_embed), dm_dict))
        ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid_channel.id]['dm_dict'] = dm_dict
        if report_user:
            egg_reports = self.bot.guild_dict[message.guild.id].setdefault('trainers', {}).setdefault(report_user.id, {}).setdefault('reports', {}).setdefault('egg', 0) + 1
            self.bot.guild_dict[message.guild.id]['trainers'][report_user.id]['reports']['egg'] = egg_reports
        return raid_channel

    async def huntr_research(self, ctx, report_details):
        message = ctx.message
        channel = ctx.channel
        author = ctx.author
        guild = ctx.guild
        research_cog = self.bot.cogs.get('Research')
        nearest_stop = ""
        location = report_details['pokestop']
        quest_coordinates = report_details['gps']
        quest = report_details['quest']
        reward = report_details['reward']
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        stop_info = ""
        if gym_matching_cog:
            stop_info, stop_location, stop_url = await gym_matching_cog.get_poi_info(ctx, location, "research", dupe_check=False, autocorrect=False)
            if stop_url:
                location = stop_location
            elif location.lower() != "unknown" and quest_coordinates not in str(gym_matching_cog.get_stops(ctx.guild.id)):
                try:
                    with open(os.path.join('data', 'stop_data.json'), 'r') as fd:
                        data = json.load(fd)
                except:
                    data = {}
                add_stop_dict = {}
                add_stop_dict[location] = {"coordinates":quest_coordinates, "alias":"", "notes":""}
                data[str(ctx.guild.id)] = {**data.get(str(ctx.guild.id), {}), **add_stop_dict}
                with open(os.path.join('data', 'stop_data.json'), 'w') as fd:
                    json.dump(data, fd, indent=2, separators=(', ', ': '))
                gym_matching_cog.gym_data = gym_matching_cog.init_json()
                gym_matching_cog.stop_data = gym_matching_cog.init_stop_json()
            elif quest_coordinates in str(gym_matching_cog.get_stops(ctx.guild.id)):
                test_stop = await gym_matching_cog.find_nearest_stop(quest_coordinates, ctx.guild.id)
                stop_info, stop_location, stop_url = await gym_matching_cog.get_poi_info(ctx, test_stop, "research", dupe_check=False, autocorrect=False)
                if stop_url:
                    location = stop_location
        if not location:
            return
        await research_cog.send_research(ctx, location, quest, reward)

    async def huntr_lure(self, ctx, report_details):
        message = ctx.message
        channel = ctx.channel
        author = ctx.author
        guild = ctx.guild
        lure_cog = self.bot.cogs.get('Lure')
        nearest_stop = ""
        location = report_details['pokestop']
        lure_coordinates = report_details['gps']
        lure_type = report_details['lure_type'].lower()
        timer = report_details.get('expire', 30)
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        stop_info = ""
        if gym_matching_cog:
            stop_info, stop_location, stop_url = await gym_matching_cog.get_poi_info(ctx, location, "lure", dupe_check=False, autocorrect=False)
            if stop_url:
                location = stop_location
            elif location.lower() != "unknown" and lure_coordinates not in str(gym_matching_cog.get_stops(ctx.guild.id)):
                try:
                    with open(os.path.join('data', 'stop_data.json'), 'r') as fd:
                        data = json.load(fd)
                except:
                    data = {}
                add_stop_dict = {}
                add_stop_dict[location] = {"coordinates":lure_coordinates, "alias":"", "notes":""}
                data[str(ctx.guild.id)] = {**data.get(str(ctx.guild.id), {}), **add_stop_dict}
                with open(os.path.join('data', 'stop_data.json'), 'w') as fd:
                    json.dump(data, fd, indent=2, separators=(', ', ': '))
                gym_matching_cog.gym_data = gym_matching_cog.init_json()
                gym_matching_cog.stop_data = gym_matching_cog.init_stop_json()
            elif lure_coordinates in str(gym_matching_cog.get_stops(ctx.guild.id)):
                test_stop = await gym_matching_cog.find_nearest_stop(lure_coordinates, ctx.guild.id)
                stop_info, stop_location, stop_url = await gym_matching_cog.get_poi_info(ctx, test_stop, "lure", dupe_check=False, autocorrect=False)
                if stop_url:
                    location = stop_location
        if not location:
            return
        await lure_cog.send_lure(ctx, lure_type, location, timer)

    async def huntr_invasion(self, ctx, report_details):
        message = ctx.message
        channel = ctx.channel
        author = ctx.author
        guild = ctx.guild
        invasion_cog = self.bot.cogs.get('Invasion')
        nearest_stop = ""
        location = report_details['pokestop']
        invasion_coordinates = report_details['gps']
        timer = report_details.get('expire', 30)
        reward = report_details.get('reward', None)
        gender = report_details.get('gender', None)
        leader = report_details.get('leader', None)
        if gender == "male" and reward == ["snorlax"]:
            reward = ["bulbasaur", "charmander", "squirtle"]
        elif gender == "female" and reward == ["snorlax"]:
            reward = ["snorlax", "lapras"]
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        stop_info = ""
        if gym_matching_cog:
            stop_info, stop_location, stop_url = await gym_matching_cog.get_poi_info(ctx, location, "lure", dupe_check=False, autocorrect=False)
            if stop_url:
                location = stop_location
            elif location.lower() != "unknown" and invasion_coordinates not in str(gym_matching_cog.get_stops(ctx.guild.id)):
                try:
                    with open(os.path.join('data', 'stop_data.json'), 'r') as fd:
                        data = json.load(fd)
                except:
                    data = {}
                add_stop_dict = {}
                add_stop_dict[location] = {"coordinates":invasion_coordinates, "alias":"", "notes":""}
                data[str(ctx.guild.id)] = {**data.get(str(ctx.guild.id), {}), **add_stop_dict}
                with open(os.path.join('data', 'stop_data.json'), 'w') as fd:
                    json.dump(data, fd, indent=2, separators=(', ', ': '))
                gym_matching_cog.gym_data = gym_matching_cog.init_json()
                gym_matching_cog.stop_data = gym_matching_cog.init_stop_json()
            elif invasion_coordinates in str(gym_matching_cog.get_stops(ctx.guild.id)):
                test_stop = await gym_matching_cog.find_nearest_stop(invasion_coordinates, ctx.guild.id)
                stop_info, stop_location, stop_url = await gym_matching_cog.get_poi_info(ctx, test_stop, "lure", dupe_check=False, autocorrect=False)
                if stop_url:
                    location = stop_location
        if not location:
            return
        if not location:
            return
        await invasion_cog.send_invasion(ctx, location, reward, gender, leader, timer)

    # @commands.command()
    # @commands.has_permissions(manage_guild=True)
    # async def huntrraid(self, ctx):
    #     """Simulates a huntr raid"""
    #     author = ctx.author
    #     guild = ctx.guild
    #     message = ctx.message
    #     channel = ctx.channel
    #     await utils.safe_delete(message)
    #     tier5 = str(ctx.bot.raid_info['raid_eggs']["5"]['pokemon'][0]).lower()
    #     description = f"**Marilla Park.**\n{tier5}\n**CP:** 60540 - **Moves:** Confusion / Shadow Ball\n*Raid Ending: 0 hours 10 min 50 sec*"
    #     url = "https://gymhuntr.com/#34.008618,-118.49125"
    #     img_url = 'https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/pkmn/150_.png?cache=1'
    #     huntrembed = discord.Embed(title=_('Level 5 Raid has started!'), description=description, url=url, colour=message.guild.me.colour)
    #     huntrembed.set_thumbnail(url=img_url)
    #     huntrmessage = await ctx.channel.send(embed=huntrembed)
    #     ctx = await self.bot.get_context(huntrmessage)
    #     await self.on_huntr(ctx)
    #
    # @commands.command()
    # @commands.has_permissions(manage_guild=True)
    # async def huntregg(self, ctx):
    #     """Simulates a huntr raid egg"""
    #     author = ctx.author
    #     guild = ctx.guild
    #     message = ctx.message
    #     channel = ctx.channel
    #     await utils.safe_delete(message)
    #     description = "**Marilla Park.**\n*Raid Starting: 0 hours 46 min 50 sec*"
    #     url = "https://gymhuntr.com/#34.008618,-118.49125"
    #     img_url = 'https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/eggs/5.png?cache=1'
    #     huntrembed = discord.Embed(title=_('Level 5 Raid is starting soon!!'), description=description, url=url, colour=message.guild.me.colour)
    #     huntrembed.set_thumbnail(url=img_url)
    #     huntrmessage = await ctx.channel.send(embed=huntrembed)
    #     ctx = await self.bot.get_context(huntrmessage)
    #     await self.on_huntr(ctx)
    #
    # @commands.command()
    # @commands.has_permissions(manage_guild=True)
    # async def huntrwild(self, ctx):
    #     """Simulates a huntr wild"""
    #     author = ctx.author
    #     guild = ctx.guild
    #     message = ctx.message
    #     channel = ctx.channel
    #     await utils.safe_delete(message)
    #     description = "Click above to view the wild\n\n*Remaining: 25 min 3 sec*\nWeather: *None*"
    #     url = "https://gymhuntr.com/#34.008618,-118.49125"
    #     img_url = 'https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/pkmn/150_.png?cache=1'
    #     huntrembed = discord.Embed(title=_('A wild Mewtwo (150) has appeared!'), description=description, url=url, colour=message.guild.me.colour)
    #     huntrembed.set_thumbnail(url=img_url)
    #     huntrmessage = await ctx.channel.send(embed=huntrembed)
    #     ctx = await self.bot.get_context(huntrmessage)
    #     await self.on_huntr(ctx)

    @commands.group(invoke_without_command=True, case_insensitive=True)
    @commands.has_permissions(manage_guild=True)
    async def alarm(self, ctx):
        pass

    @alarm.command()
    @commands.has_permissions(manage_guild=True)
    async def filter(self, ctx, filter_type=None):
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        error = False
        first = True
        raid_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/tx_raid_coin.png?cache=1')
        raid_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        while True:
            async with ctx.typing():
                def check(reply):
                    if reply.author is not guild.me and reply.channel.id == channel.id and reply.author == message.author:
                        return True
                    else:
                        return False
                if not filter_type or filter_type.lower() not in ["wild", "egg", "raid", "invasion", "research", "lure"]:
                    raid_embed.clear_fields()
                    raid_embed.add_field(name=_('**New Alarm Filter**'), value=_("Meowth! I'll help you add an Alarm Filter.\n\nFirst, I'll need to know what **type** of filter you'd like to add. Reply with **wild, egg, raid, invasion, research, or lure**. You can reply with **cancel** to stop anytime."), inline=False)
                    filter_type_wait = await channel.send(embed=raid_embed)
                    try:
                        filter_type_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        filter_type_msg = None
                    await utils.safe_delete(filter_type_wait)
                    if not filter_type_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(filter_type_msg)
                    if filter_type_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif filter_type_msg.clean_content.lower() not in ["wild", "egg", "raid", "invasion", "research", "lure"]:
                        raid_embed.clear_fields()
                        raid_embed.add_field(name=_('**New Alarm Filter**'), value=f"Meowth! I couldn't understand your filter type! Retry or reply with **cancel**.", inline=False)
                        await channel.send(embed=raid_embed, delete_after=20)
                        continue
                    else:
                        filter_type = filter_type_msg.clean_content.lower()
                if filter_type and filter_type == "wild":
                    current_filter = self.bot.guild_dict[ctx.guild.id]['configure_dict']['scanners'].setdefault('filters', {}).setdefault('wild', [])
                    raid_embed.clear_fields()
                    raid_embed.add_field(name=_('**New Wild Filter**'), value=f"If you don't have direct control over your reporting bot, you may want to blacklist some of its reports. Reports with IV will still be posted. Please enter a list of wild pokemon to block automatic reports of or reply with **N** to disable the filter.\n\n**Current Filter**:\n\n{str(current_filter)}")
                    filter_type_wait = await channel.send(embed=raid_embed)
                    wildfilter_list = []
                    wildfilter_names = []
                    while True:
                        try:
                            filter_type_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            filter_type_msg = None
                        await utils.safe_delete(filter_type_wait)
                        if not filter_type_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(filter_type_msg)
                        if filter_type_msg.clean_content.lower() == "cancel":
                            error = _("cancelled the report")
                            break
                        elif filter_type_msg.content.lower() == 'n':
                            self.bot.guild_dict[ctx.guild.id]['configure_dict']['scanners']['filters']['wild'] = []
                            raid_embed.clear_fields()
                            raid_embed.add_field(name=_('**New Wild Filter**'), value=f"Automatic wild filter disabled")
                            await channel.send(embed=raid_embed, delete_after=60)
                        else:
                            wildfilter_list = filter_type_msg.content.lower().split(',')
                            for pkmn in wildfilter_list:
                                pokemon = await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, pkmn, allow_digits=True)
                                if pokemon:
                                    if not pokemon.form and not pokemon.region and not pokemon.size and not pokemon.gender and not pokemon.shadow:
                                        if pokemon.id not in current_filter:
                                            current_filter.append(pokemon.id)
                                            wildfilter_names.append(f"{pokemon.name} (all forms)")
                                    else:
                                        if str(pokemon) not in current_filter:
                                            current_filter.append(str(pokemon))
                                            wildfilter_names.append(str(pokemon))
                            if len(wildfilter_names) > 0:
                                raid_embed.clear_fields()
                                raid_embed.add_field(name=_('**New Wild Filter**'), value=f"Automatic wild filter will block: {', '.join(wildfilter_names)}")
                                await channel.send(embed=raid_embed, delete_after=60)
                                self.bot.guild_dict[ctx.guild.id]['configure_dict']['scanners']['filters']['wild'] = current_filter
                                break
                            else:
                                raid_embed.clear_fields()
                                raid_embed.add_field(name=_('**New Wild Filter**'), value=f"Please enter at least one pokemon or **N** to turn off automatic wild filter.")
                                await channel.send(embed=raid_embed, delete_after=60)
                                continue
                        break
                if filter_type and filter_type == "raid":
                    current_filter = self.bot.guild_dict[ctx.guild.id]['configure_dict']['scanners'].setdefault('filters', {}).setdefault('raid', [])
                    raid_embed.clear_fields()
                    raid_embed.add_field(name=_('**New raid Filter**'), value=f"If you don't have direct control over your reporting bot, you may want to blacklist some of its reports. Please enter a list of raid pokemon to block automatic reports of or reply with **N** to disable the filter.\n\n**Current Filter**:\n\n{str(current_filter)}")
                    filter_type_wait = await channel.send(embed=raid_embed)
                    raidfilter_list = []
                    raidfilter_names = []
                    while True:
                        try:
                            filter_type_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            filter_type_msg = None
                        await utils.safe_delete(filter_type_wait)
                        if not filter_type_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(filter_type_msg)
                        if filter_type_msg.clean_content.lower() == "cancel":
                            error = _("cancelled the report")
                            break
                        elif filter_type_msg.content.lower() == 'n':
                            self.bot.guild_dict[ctx.guild.id]['configure_dict']['scanners']['filters']['raid'] = []
                            raid_embed.clear_fields()
                            raid_embed.add_field(name=_('**New raid Filter**'), value=f"Automatic raid filter disabled")
                            await channel.send(embed=raid_embed, delete_after=60)
                        else:
                            raidfilter_list = filter_type_msg.content.lower().split(',')
                            for pkmn in raidfilter_list:
                                pokemon = await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, pkmn, allow_digits=True)
                                if pokemon:
                                    if not pokemon.form and not pokemon.region and not pokemon.size and not pokemon.gender and not pokemon.shadow:
                                        if pokemon.id not in current_filter:
                                            current_filter.append(pokemon.id)
                                            raidfilter_names.append(f"{pokemon.name} (all forms)")
                                    else:
                                        if str(pokemon) not in current_filter:
                                            current_filter.append(str(pokemon))
                                            raidfilter_names.append(str(pokemon))
                            if len(raidfilter_names) > 0:
                                raid_embed.clear_fields()
                                raid_embed.add_field(name=_('**New raid Filter**'), value=f"Automatic raid filter will block: {', '.join(raidfilter_names)}")
                                await channel.send(embed=raid_embed, delete_after=60)
                                self.bot.guild_dict[ctx.guild.id]['configure_dict']['scanners']['filters']['raid'] = current_filter
                                break
                            else:
                                raid_embed.clear_fields()
                                raid_embed.add_field(name=_('**New raid Filter**'), value=f"Please enter at least one pokemon or **N** to turn off automatic raid filter.")
                                await channel.send(embed=raid_embed, delete_after=60)
                                continue
                        break
                elif filter_type and filter_type == "egg":
                    current_filter = self.bot.guild_dict[ctx.guild.id]['configure_dict']['scanners'].setdefault('filters', {}).setdefault('egg', [])
                    raid_embed.clear_fields()
                    raid_embed.add_field(name=_('**New Egg Filter**'), value=f"If you don't have direct control over your reporting bot, you may want to blacklist some of its reports. Please enter a list of egg levels to block automatic reports of or reply with **N** to disable the filter.\n\n**Current Filter**:\n\n{str(current_filter)}")
                    filter_type_wait = await channel.send(embed=raid_embed)
                    eggfilter_list = []
                    while True:
                        try:
                            filter_type_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            filter_type_msg = None
                        await utils.safe_delete(filter_type_wait)
                        if not filter_type_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(filter_type_msg)
                        if filter_type_msg.clean_content.lower() == "cancel":
                            error = _("cancelled the report")
                            break
                        elif filter_type_msg.content.lower() == 'n':
                            self.bot.guild_dict[ctx.guild.id]['configure_dict']['scanners']['filters']['egg'] = []
                            raid_embed.clear_fields()
                            raid_embed.add_field(name=_('**New Egg Filter**'), value=f"Automatic Egg filter disabled")
                            await channel.send(embed=raid_embed, delete_after=60)
                        else:
                            eggfilter_list = filter_type_msg.content.lower().split(',')
                            eggfilter_list = [x for x in eggfilter_list if x in ["1", "2", "3", "4", "5"]]
                            if len(eggfilter_list) > 0:
                                raid_embed.clear_fields()
                                raid_embed.add_field(name=_('**New Egg Filter**'), value=f"Automatic Egg filter will block: {', '.join(eggfilter_list)}")
                                await channel.send(embed=raid_embed, delete_after=60)
                                self.bot.guild_dict[ctx.guild.id]['configure_dict']['scanners']['filters']['egg'] = eggfilter_list
                                break
                            else:
                                raid_embed.clear_fields()
                                raid_embed.add_field(name=_('**New Egg Filter**'), value=f"Please enter at least one level or **N** to turn off automatic Egg filter.")
                                await channel.send(embed=raid_embed, delete_after=60)
                                continue
                        break
                elif filter_type and filter_type == "lure":
                    current_filter = self.bot.guild_dict[ctx.guild.id]['configure_dict']['scanners'].setdefault('filters', {}).setdefault('lure', [])
                    raid_embed.clear_fields()
                    raid_embed.add_field(name=_('**New lure Filter**'), value=f"If you don't have direct control over your reporting bot, you may want to blacklist some of its reports. Please enter a list of lure types to block automatic reports of or reply with **N** to disable the filter.\n\n**Current Filter**:\n\n{str(current_filter)}")
                    filter_type_wait = await channel.send(embed=raid_embed)
                    lurefilter_list = []
                    while True:
                        try:
                            filter_type_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            filter_type_msg = None
                        await utils.safe_delete(filter_type_wait)
                        if not filter_type_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(filter_type_msg)
                        if filter_type_msg.clean_content.lower() == "cancel":
                            error = _("cancelled the report")
                            break
                        elif filter_type_msg.content.lower() == 'n':
                            self.bot.guild_dict[ctx.guild.id]['configure_dict']['scanners']['filters']['lure'] = []
                            raid_embed.clear_fields()
                            raid_embed.add_field(name=_('**New lure Filter**'), value=f"Automatic lure filter disabled")
                            await channel.send(embed=raid_embed, delete_after=60)
                        else:
                            lurefilter_list = filter_type_msg.content.lower().split(',')
                            lurefilter_list = [x for x in lurefilter_list if x in ["normal", "magnetic", "mossy", "glacial"]]
                            if len(lurefilter_list) > 0:
                                raid_embed.clear_fields()
                                raid_embed.add_field(name=_('**New lure Filter**'), value=f"Automatic lure filter will block: {', '.join(lurefilter_list)}")
                                await channel.send(embed=raid_embed, delete_after=60)
                                self.bot.guild_dict[ctx.guild.id]['configure_dict']['scanners']['filters']['lure'] = lurefilter_list
                                break
                            else:
                                raid_embed.clear_fields()
                                raid_embed.add_field(name=_('**New lure Filter**'), value=f"Please enter at least one level or **N** to turn off automatic lure filter.")
                                await channel.send(embed=raid_embed, delete_after=60)
                                continue
                        break
                elif filter_type and filter_type == "invasion":
                    current_filter = self.bot.guild_dict[ctx.guild.id]['configure_dict']['scanners'].setdefault('filters', {}).setdefault('invasion', [])
                    raid_embed.clear_fields()
                    raid_embed.add_field(name=_('**New invasion Filter**'), value=f"If you don't have direct control over your reporting bot, you may want to blacklist some of its reports. Please enter a list of invasion types to block automatic reports of or reply with **N** to disable the filter.\n\n**Current Filter**:\n\n{str(current_filter)}")
                    filter_type_wait = await channel.send(embed=raid_embed)
                    invasionfilter_list = []
                    while True:
                        try:
                            filter_type_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            filter_type_msg = None
                        await utils.safe_delete(filter_type_wait)
                        if not filter_type_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(filter_type_msg)
                        if filter_type_msg.clean_content.lower() == "cancel":
                            error = _("cancelled the report")
                            break
                        elif filter_type_msg.content.lower() == 'n':
                            self.bot.guild_dict[ctx.guild.id]['configure_dict']['scanners']['filters']['invasion'] = []
                            raid_embed.clear_fields()
                            raid_embed.add_field(name=_('**New invasion Filter**'), value=f"Automatic invasion filter disabled")
                            await channel.send(embed=raid_embed, delete_after=60)
                        else:
                            invasionfilter_list = filter_type_msg.content.lower().split(',')
                            invasionfilter_list = [x for x in invasionfilter_list if x in self.bot.type_list]
                            if len(invasionfilter_list) > 0:
                                raid_embed.clear_fields()
                                raid_embed.add_field(name=_('**New invasion Filter**'), value=f"Automatic invasion filter will block: {', '.join(invasionfilter_list)}")
                                await channel.send(embed=raid_embed, delete_after=60)
                                self.bot.guild_dict[ctx.guild.id]['configure_dict']['scanners']['filters']['invasion'] = invasionfilter_list
                                break
                            else:
                                raid_embed.clear_fields()
                                raid_embed.add_field(name=_('**New invasion Filter**'), value=f"Please enter at least one level or **N** to turn off automatic invasion filter.")
                                await channel.send(embed=raid_embed, delete_after=60)
                                continue
                        break
                elif filter_type and filter_type == "research":
                    current_filter = self.bot.guild_dict[ctx.guild.id]['configure_dict']['scanners'].setdefault('filters', {}).setdefault('research', [])
                    raid_embed.clear_fields()
                    raid_embed.add_field(name=_('**New research Filter**'), value=f"If you don't have direct control over your reporting bot, you may want to blacklist some of its reports. Please enter a list of research rewrds (pokemon or items) to block automatic reports of or reply with **N** to disable the filter.\n\n**Current Filter**:\n\n{str(current_filter)}")
                    filter_type_wait = await channel.send(embed=raid_embed)
                    researchfilter_list = []
                    researchfilter_names = []
                    while True:
                        try:
                            filter_type_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            filter_type_msg = None
                        await utils.safe_delete(filter_type_wait)
                        if not filter_type_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(filter_type_msg)
                        if filter_type_msg.clean_content.lower() == "cancel":
                            error = _("cancelled the report")
                            break
                        elif filter_type_msg.content.lower() == 'n':
                            self.bot.guild_dict[ctx.guild.id]['configure_dict']['scanners']['filters']['research'] = []
                            raid_embed.clear_fields()
                            raid_embed.add_field(name=_('**New Research Filter**'), value=f"Automatic research filter disabled")
                            await channel.send(embed=raid_embed, delete_after=60)
                        else:
                            researchfilter_list = filter_type_msg.content.lower().split(',')
                            for reward in researchfilter_list:
                                __, item_name = await utils.get_item(reward)
                                if item_name and item_name not in current_filter:
                                    current_filter.append(item_name)
                                    researchfilter_names.append(item_name.title())
                                else:
                                    pokemon = await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, reward, allow_digits=True)
                                    if pokemon:
                                        if not pokemon.form and not pokemon.region and not pokemon.size and not pokemon.gender and not pokemon.shadow:
                                            if pokemon.id not in current_filter:
                                                current_filter.append(pokemon.id)
                                                researchfilter_names.append(f"{pokemon.name} (all forms)")
                                        else:
                                            if str(pokemon) not in current_filter:
                                                current_filter.append(str(pokemon))
                                                researchfilter_names.append(str(pokemon))
                                if len(researchfilter_names) > 0:
                                    raid_embed.clear_fields()
                                    raid_embed.add_field(name=_('**New research Filter**'), value=f"Automatic research filter will block: {', '.join(researchfilter_names)}")
                                    await channel.send(embed=raid_embed, delete_after=60)
                                    self.bot.guild_dict[ctx.guild.id]['configure_dict']['scanners']['filters']['research'] = current_filter
                                    break
                                else:
                                    raid_embed.clear_fields()
                                    raid_embed.add_field(name=_('**New research Filter**'), value=f"Please enter at least one research reward or **N** to turn off automatic research filter.")
                                    await channel.send(embed=raid_embed, delete_after=60)
                                    continue
                        break
            break

    @alarm.command()
    @commands.has_permissions(manage_guild=True)
    async def forward(self, ctx):
        timestamp = (ctx.message.created_at + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        raid_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/tx_raid_coin.png?cache=1')
        def check(reply):
            if reply.author is not ctx.guild.me and reply.channel.id == ctx.channel.id and reply.author == ctx.author:
                return True
            else:
                return False
        await utils.safe_delete(ctx.message)
        current_overwrites = self.bot.guild_dict[ctx.guild.id].setdefault('configure_dict', {}).setdefault('scanners', {}).setdefault('forwarding', {})
        raid_embed.add_field(name=f"**Current Forwarding Channels**", value=f"")
        overwrite_str = ""
        for overwrite in current_overwrites:
            if len(overwrite_str) < 1000:
                overwrite_str += f"{self.bot.get_channel(overwrite).mention} = {self.bot.get_channel(current_overwrites[overwrite]).mention}\n"
                raid_embed.set_field_at(0, name=f"**Current Forwarding Channels**", value=overwrite_str)
            else:
                await ctx.send(embed=raid_embed, delete_after=60)
                overwrite_str = f"{self.bot.get_channel(overwrite).mention} = {self.bot.get_channel(current_overwrites[overwrite]).mention}\n"
        if current_overwrites:
            await ctx.send(embed=raid_embed, delete_after=60)
        new_overwrites = {}
        raid_embed.clear_fields()
        raid_embed.set_footer(text=_('Sent by @{author} - {timestamp}').format(author=ctx.author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=ctx.author.avatar_url_as(format=None, static_format='jpg', size=32))
        raid_embed.add_field(name=_('**Edit Alarm Forwarding**'), value=f"Meowth! I will help you edit alarm channel forwarding! This is useful if want to send all **!alarm** messages sent by a bot in one channel and instead forward them to another channel. If a channel is not on this list, the **!alarm** message will be sent in the channel it is received.\n\n{'The current list is listed above.' if current_overwrites else 'You have no current forwarding channels.'}\n\nThe correct format for this is:\n`Receiving Channel = Forward Channel`\n\nReply with any overwrites to add to my current list, **reset** to remove all overwrites, or **cancel** to stop anytime.", inline=False)
        forward_list_wait = await ctx.send(embed=raid_embed)
        try:
            forward_list_msg = await self.bot.wait_for('message', timeout=60, check=check)
        except asyncio.TimeoutError:
            forward_list_msg = None
        await utils.safe_delete(forward_list_wait)
        if not forward_list_msg:
            raid_embed.clear_fields()
            raid_embed.add_field(name=_('**Alarm Forwarding Cancelled**'), value=_("Meowth! Your edit has been cancelled because you took too long to respond! Retry when you're ready."), inline=False)
            return await ctx.send(embed=raid_embed, delete_after=10)
        else:
            await utils.safe_delete(forward_list_msg)
        if forward_list_msg.clean_content.lower() == "cancel":
            raid_embed.clear_fields()
            raid_embed.add_field(name=_('**Alarm Forwarding Cancelled**'), value=_("Meowth! Your edit has been cancelled because you canceled the report! Retry when you're ready."), inline=False)
            return await ctx.send(embed=raid_embed, delete_after=10)
        elif forward_list_msg.clean_content.lower() == "reset":
            new_overwrites = {}
        else:
            overwrite_list = forward_list_msg.content.split(',')
            overwrite_list = [x.strip() for x in overwrite_list]
            for overwrite in overwrite_list:
                if len(overwrite.split('=')) != 2:
                    raid_embed.clear_fields()
                    raid_embed.add_field(name=_('**Alarm Forwarding Cancelled**'), value=_("Meowth! Your edit has been cancelled because you entered an incorrect format! Retry when you're ready."), inline=False)
                    return await ctx.send(embed=raid_embed, delete_after=10)
                converter = commands.TextChannelConverter()
                try:
                    to_replace = await converter.convert(ctx, overwrite.split('=')[0].strip())
                except:
                    to_replace = None
                try:
                    replace_with = await converter.convert(ctx, overwrite.split('=')[1].strip())
                except:
                    replace_with = None
                if not to_replace or not replace_with:
                    continue
                else:
                    new_overwrites[to_replace.id] = replace_with.id
                new_overwrites = {**current_overwrites, **new_overwrites}
        if new_overwrites or forward_list_msg.clean_content.lower() == "reset":
            self.bot.guild_dict[ctx.guild.id]['configure_dict']['scanners']['forwarding'] = new_overwrites
            raid_embed.clear_fields()
            raid_embed.add_field(name=_('**Alarm Forwarding Successful**'), value=_("Meowth! Your forwarding settings were successful!"), inline=False)
            return await ctx.send(embed=raid_embed, delete_after=10)

    @alarm.command()
    async def recover(self, ctx):
        """Recovers bot reports that Meowth missed."""
        message_list = []
        await utils.safe_delete(ctx.message)
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
        async with ctx.channel.typing():
            async for message in ctx.channel.history(limit=500, oldest_first=False):
                if len(message_list) > 90:
                    await utils.safe_bulk_delete(ctx.channel, message_list)
                    message_list = []
                if message.content.lower().startswith('!alarm') and "{" in message.content and "}" in message.content:
                    message.content = message.content.replace("!alarm","").strip()
                    timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
                    try:
                        report_details = json.loads(message.content)
                    except:
                        return
                    if report_details['type'] == "research":
                        if timestamp.day == now.day:
                            ctx.message = message
                            await self.on_pokealarm(ctx)
                        elif relativedelta(now, timestamp).days < 14:
                            message_list.append(message)
                    elif report_details['type'] == "raid" or report_details['type'] == "egg":
                        raid_expire = timestamp + datetime.timedelta(minutes=report_details.get('raidexp', 0))
                        if raid_expire > now:
                            timediff = relativedelta(raid_expire, now)
                            report_details['raidexp'] = timediff.minutes
                            ctx.message = message
                            ctx.message.content = "!alarm " + str(report_details).replace("'", '"')
                            await self.on_pokealarm(ctx)
                        elif relativedelta(now, timestamp).days < 14:
                            message_list.append(message)
                    elif report_details['type'] == "invasion" or report_details['type'] == "lure":
                        report_expire = timestamp + datetime.timedelta(minutes=report_details.get('expire', 0))
                        if report_expire > now:
                            timediff = relativedelta(report_expire, now)
                            report_details['expire'] = timediff.minutes
                            ctx.message = message
                            ctx.message.content = "!alarm " + str(report_details).replace("'", '"')
                            await self.on_pokealarm(ctx)
                        elif relativedelta(now, timestamp).days < 14:
                            message_list.append(message)
                    elif report_details['type'] == "wild":
                        report_expire = report_details.get('expire', "0 min 0 sec")
                        report_expire = timestamp + datetime.timedelta(minutes=int(report_expire.split()[0]), seconds=int(report_expire.split()[2]))
                        if report_expire > now:
                            timediff = relativedelta(report_expire, now)
                            report_details['expire'] = f"{timediff.minutes} min {timediff.seconds} sec"
                            ctx.message = message
                            ctx.message.content = "!alarm " + str(report_details).replace("'", '"')
                            await self.on_pokealarm(ctx)
                        elif relativedelta(now, timestamp).days < 14:
                            message_list.append(message)
            await utils.safe_bulk_delete(ctx.channel, message_list)

    @alarm.command()
    @commands.has_permissions(manage_guild=True)
    async def raid(self, ctx):
        """Simulates an alarm raid"""
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        await utils.safe_delete(message)
        random_raid = random.choice(ctx.bot.raid_info['raid_eggs']["5"]['pokemon'])
        pokemon = await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, random_raid)
        embed = discord.Embed(title="Title", description="Embed Description")
        huntrmessage = await ctx.channel.send('!alarm ' + str({"type":"raid", "pokemon":random_raid, "gym":"Marilla Park", "gps":"39.628941,-79.935063", "moves":f"{pokemon.quick_moves[0].title()} / {pokemon.charge_moves[0].title()}", "raidexp":10}).replace("'", '"'), embed=embed)
        ctx = await self.bot.get_context(huntrmessage)
        await self.on_pokealarm(ctx)

    @alarm.command()
    @commands.has_permissions(manage_guild=True)
    async def egg(self, ctx, level="5"):
        """Simulates an alarm egg"""
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        await utils.safe_delete(message)
        embed = discord.Embed(title="Title", description="Embed Description")
        if not level.isdigit() or int(level) > 5:
            level = 5
        huntrmessage = await ctx.channel.send('!alarm {"type":"egg", "level":"' + level + '", "gym":"Marilla Park", "gps":"39.628941,-79.935063", "raidexp":10}', embed=embed)
        ctx = await self.bot.get_context(huntrmessage)
        await self.on_pokealarm(ctx)

    @alarm.command()
    @commands.has_permissions(manage_guild=True)
    async def wild(self, ctx):
        """Simulates an alarm wild"""
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        await utils.safe_delete(message)
        huntrmessage = await ctx.channel.send('!alarm {"type":"wild", "pokemon":"Ditto (Weedle)", "gps":"39.637087,-79.954375", "expire":"5 min 0 sec","gender":"male", "height":"0.33m", "weight":"4.6kg", "moveset":"Quick Attack / Wild Charge", "weather":"snowy"}')
        ctx = await self.bot.get_context(huntrmessage)
        await self.on_pokealarm(ctx)

    @alarm.command()
    @commands.has_permissions(manage_guild=True)
    async def wildiv(self, ctx):
        """Simulates an alarm wild"""
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        await utils.safe_delete(message)
        huntrmessage = await ctx.channel.send('!alarm {"type":"wild", "pokemon":"XL Rattata", "gps":"39.637087,-79.954375", "expire":"5 min 0 sec","gender":"male", "height":"0.33m", "weight":"4.6kg", "moveset":"Quick Attack / Wild Charge", "weather":"snowy", "iv_percent":"100"}')
        ctx = await self.bot.get_context(huntrmessage)
        await self.on_pokealarm(ctx)

    @alarm.command()
    @commands.has_permissions(manage_guild=True)
    async def quest(self, ctx):
        """Simulates an alarm quest"""
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        await utils.safe_delete(message)
        huntrmessage = await ctx.channel.send('!alarm {"type":"research", "pokestop":"Disney Park", "gps":"39.645742,-79.36908", "quest":"Catch 5 Electric Pokemon", "reward":"Pikachu Encounter"}')
        ctx = await self.bot.get_context(huntrmessage)
        await self.on_pokealarm(ctx)

    @alarm.command()
    @commands.has_permissions(manage_guild=True)
    async def lure(self, ctx):
        """Simulates an alarm lure"""
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        lures = ['normal', 'mossy', 'glacial', 'magnetic']
        random_lure = random.choice(lures)
        await utils.safe_delete(message)
        huntrmessage = await ctx.channel.send('!alarm ' + str({"type":"lure", "pokestop":"Marilla Park", "gps":"39.645742,-79.96908", "lure_type":random_lure, "expire":25}).replace("'", '"'))
        ctx = await self.bot.get_context(huntrmessage)
        await self.on_pokealarm(ctx)

    @alarm.command()
    @commands.has_permissions(manage_guild=True)
    async def invasion(self, ctx):
        """Simulates an alarm invasion"""
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        await utils.safe_delete(message)
        random_type = random.choice(self.bot.type_list)
        huntrmessage = await ctx.channel.send('!alarm ' + str({"type":"invasion", "pokestop":"Marilla Park", "reward":"ground", "gps":"39.645742,-79.96908", "gender":"female", "expire":25}).replace("'", '"'))
        ctx = await self.bot.get_context(huntrmessage)
        await self.on_pokealarm(ctx)

    @tasks.loop(seconds=300)
    async def raidhour_check(self, loop=True):
        for guild in self.bot.guilds:
            if guild.id not in list(self.bot.guild_dict.keys()):
                continue
            try:
                for event in list(self.bot.guild_dict[guild.id].get('raidhour_dict', {}).keys()):
                    if event in self.bot.active_raidhours:
                        continue
                    self.bot.loop.create_task(self.raidhour_manager(guild.id, event))
                    self.bot.active_raidhours.append(event)
            except Exception as e:
                print(traceback.format_exc())
        if not loop:
            return

    @raidhour_check.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

    async def raidhour_manager(self, guild_id, event_id):
        try:
            guild = self.bot.get_guild(guild_id)
            event_dict = copy.deepcopy(self.bot.guild_dict[guild.id]['raidhour_dict'][event_id])
            raid_cog = self.bot.cogs.get('Raid')
            if not raid_cog:
                return
            report_channel = self.bot.get_channel(event_dict['report_channel'])
            try:
                report_message = await report_channel.fetch_message(event_id)
                ctx = await self.bot.get_context(report_message)
            except:
                self.bot.active_raidhours.remove(event_id)
                del self.bot.guild_dict[guild.id]['raidhour_dict'][event_id]
                return
            report_author = guild.get_member(event_dict['report_author'])
            bot_account = guild.get_member(event_dict['bot_account'])
            bot_channel = self.bot.get_channel(event_dict['bot_channel'])
            channels_made = False
            while True:
                now = datetime.datetime.utcnow()
                wait_time = [600]
                if event_id not in self.bot.guild_dict[guild.id]['raidhour_dict']:
                    self.bot.active_raidhours.remove(event_id)
                    del self.bot.guild_dict[guild.id]['raidhour_dict'][event_id]
                    return
                event_dict = copy.deepcopy(self.bot.guild_dict[guild.id]['raidhour_dict'][event_id])
                if self.bot.guild_dict[guild.id]['raidhour_dict'][event_id].get('currently_active'):
                    channels_made = True
                if (event_dict['make_trains'] or event_dict.get('make_meetups')) and not channels_made:
                    if time.time() >= event_dict['channel_time']:
                        event_start = datetime.datetime.utcfromtimestamp(event_dict['event_start']) + datetime.timedelta(hours=self.bot.guild_dict[guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
                        event_end = datetime.datetime.utcfromtimestamp(event_dict['event_end']) + datetime.timedelta(hours=self.bot.guild_dict[guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
                        train_channel = self.bot.get_channel(event_dict['train_channel'])
                        for location in event_dict['event_locations']:
                            ctx.author, ctx.message.author = report_author, report_author
                            ctx.channel, ctx.message.channel = train_channel, train_channel
                            ctx.raidhour = True
                            if event_dict['make_trains']:
                                ctx.command = self.bot.get_command("train")
                                channel = await raid_cog._train_channel(ctx, location)
                            elif event_dict.get('make_meetups'):
                                ctx.command = self.bot.get_command("meetup")
                                channel = await raid_cog._meetup(ctx, location)
                            ctx.channel, ctx.message.channel = channel, channel
                            await ctx.invoke(self.bot.get_command("meetup title"), title=f"{location} - {event_dict['event_title']}")
                            await ctx.invoke(self.bot.get_command("starttime"), start_time=event_start.strftime('%B %d %I:%M %p'))
                            await ctx.invoke(self.bot.get_command("timerset"), timer=event_end.strftime('%B %d %I:%M %p'))
                        self.bot.guild_dict[guild.id]['raidhour_dict'][event_id]['currently_active'] = True
                        channels_made = True
                    else:
                        wait_time.append(event_dict['channel_time'] - time.time())
                if event_dict.get('event_pokemon'):
                    for pokemon in event_dict['event_pokemon']:
                        if pokemon not in self.bot.guild_dict[guild.id]['configure_dict']['scanners']['filters']['wild']:
                            self.bot.guild_dict[guild.id]['configure_dict']['scanners']['filters']['wild'].append(pokemon)
                if bot_account:
                    if time.time() < event_dict['mute_time']:
                        wait_time.append(event_dict['mute_time'] - time.time())
                if time.time() >= event_dict['event_end']:
                    try:
                        user_message = await report_channel.fetch_message(event_dict['user_message'])
                        await utils.safe_delete(user_message)
                    except:
                        pass
                    try:
                        self.bot.guild_dict[guild.id]['configure_dict']['scanners']['filters']['wild'].remove(event_dict['event_pokemon'])
                    except:
                        pass
                    try:
                        self.bot.active_raidhours.remove(event_id)
                    except:
                        pass
                    if self.bot.guild_dict[ctx.guild.id]['raidhour_dict'][event_id].get('recur_weekly', False):
                        self.bot.guild_dict[ctx.guild.id]['raidhour_dict'][event_id]['mute_time'] = self.bot.guild_dict[ctx.guild.id]['raidhour_dict'][event_id]['mute_time'] + 7*24*60*60
                        self.bot.guild_dict[ctx.guild.id]['raidhour_dict'][event_id]['event_start'] = self.bot.guild_dict[ctx.guild.id]['raidhour_dict'][event_id]['event_start'] + 7*24*60*60
                        self.bot.guild_dict[ctx.guild.id]['raidhour_dict'][event_id]['event_end'] = self.bot.guild_dict[ctx.guild.id]['raidhour_dict'][event_id]['event_end'] + 7*24*60*60
                        self.bot.guild_dict[ctx.guild.id]['raidhour_dict'][event_id]['channel_time'] = self.bot.guild_dict[ctx.guild.id]['raidhour_dict'][event_id]['channel_time'] + 7*24*60*60
                        self.bot.guild_dict[guild.id]['raidhour_dict'][event_id]['currently_active'] = False
                    else:
                        try:
                            del self.bot.guild_dict[guild.id]['raidhour_dict'][event_id]
                        except:
                            pass
                    return
                else:
                    wait_time.append(event_dict['event_end'] - time.time())
                wait_time = [x for x in wait_time if x > 0]
                if not wait_time:
                    wait_time = [600]
                await asyncio.sleep(min(wait_time))
        except KeyError:
            return

    @commands.group(invoke_without_command=True, case_insensitive=True, aliases=["commday"])
    @checks.is_mod()
    async def raidhour(self, ctx):
        """Schedule events such as raid hours or community days."""
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        raid_cog = self.bot.cogs.get('Raid')
        if not raid_cog:
            return
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        error = False
        first = True
        event_dict = {
            "report_author":ctx.author.id,
            "report_channel":ctx.channel.id,
            "user_message":ctx.message.id,
            "bot_account": None,
            "bot_channel": None,
            "mute_time": None,
            "event_start": None,
            "event_end": None,
            "make_trains": None,
            "train_channel":None,
            "channel_time": None,
            "event_title": None,
            "event_locations": [],
            "event_pokemon": [],
            "event_pokemon_str": "",
            "recur_weekly": None,
            "egg_level": None
        }
        raid_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/tx_raid_coin.png?cache=1')
        raid_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        while True:
            async with ctx.typing():
                def check(reply):
                    if reply.author is not guild.me and reply.channel.id == channel.id and reply.author == message.author:
                        return True
                    else:
                        return False
                if event_dict.get('bot_account') == None:
                    raid_embed.clear_fields()
                    raid_embed.add_field(name=_('**New Raid Hour Report**'), value=_("Meowth! I'll help you schedule a raid hour, raid day, or other event! This will allow you to mute a given bot account in a given channel during a certain time. I'll also help you make Raid Train or Meetup channels if you'd like.\n\nFirst, I'll need to know what **bot account** you'd like to mute. Reply with a @mention, ID, or case-sensitive Username of the bot or **none** to not mute a bot and just schedule channels. You can reply with **cancel** to stop anytime."), inline=False)
                    bot_account_wait = await channel.send(embed=raid_embed)
                    try:
                        bot_account_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        bot_account_msg = None
                    await utils.safe_delete(bot_account_wait)
                    if not bot_account_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(bot_account_msg)
                    if bot_account_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif bot_account_msg.clean_content.lower() == "none":
                        event_dict['bot_account'] = False
                        bot_account = None
                        event_dict['bot_channel'] = False
                    else:
                        converter = commands.MemberConverter()
                        try:
                            bot_account = await converter.convert(ctx, bot_account_msg.content)
                            event_dict['bot_account'] = bot_account.id
                        except:
                            raid_embed.clear_fields()
                            raid_embed.add_field(name=_('**New Raid Hour Report**'), value=f"Meowth! I couldn't find that account! Retry or reply with **cancel**.", inline=False)
                            bot_account_wait = await channel.send(embed=raid_embed, delete_after=20)
                            continue
                        if bot_account == ctx.guild.me:
                            error = _("entered my account")
                            break
                        elif not bot_account.bot:
                            error = _("entered a human account")
                            break
                if event_dict.get('bot_channel') == None:
                    raid_embed.clear_fields()
                    raid_embed.add_field(name=_('**New Raid Hour Report**'), value=f"Meowth! Next, I'll need to know what **bot channel** you'd like to mute {bot_account.mention} in. Reply with a #mention, ID, or case-sensitive name of the channel. You can reply with **cancel** to stop anytime.", inline=False)
                    bot_channel_wait = await channel.send(embed=raid_embed)
                    try:
                        bot_channel_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        bot_channel_msg = None
                    await utils.safe_delete(bot_channel_wait)
                    if not bot_channel_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(bot_channel_msg)
                    if bot_channel_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    else:
                        converter = commands.TextChannelConverter()
                        try:
                            bot_channel = await converter.convert(ctx, bot_channel_msg.content)
                            event_dict['bot_channel'] = bot_channel.id
                        except:
                            raid_embed.clear_fields()
                            raid_embed.add_field(name=_('**New Raid Hour Report**'), value=f"Meowth! I couldn't find that channel! Retry or reply with **cancel**.", inline=False)
                            bot_channel_wait = await channel.send(embed=raid_embed, delete_after=20)
                            continue
                if event_dict.get('bot_account') and event_dict.get('bot_channel') and event_dict.get('egg_level') == None:
                    raid_embed.clear_fields()
                    raid_embed.add_field(name=_('**New Raid Hour Report**'), value=f"Now, are there specific **raid levels** that you'd like to block {bot_account.mention} from posting in {bot_channel.mention}? Reply with **all** to block all raids or reply with a comma separated list of egg levels 1-5. Any blocked raids will be reported internally, but will not get a channel. You can reply with **cancel** to stop anytime.", inline=False)
                    raid_level_wait = await channel.send(embed=raid_embed)
                    try:
                        raid_level_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        raid_level_msg = None
                    await utils.safe_delete(raid_level_wait)
                    if not raid_level_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(raid_level_msg)
                    if raid_level_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif raid_level_msg.clean_content.lower() == "all":
                        event_dict['egg_level'] = [0]
                    else:
                        level_list = raid_level_msg.clean_content.lower().split(',')
                        level_list = [x.strip() for x in level_list]
                        level_list = [int(x) for x in level_list if x.isdigit()]
                        level_list = [x for x in level_list if x > 0 and x <= 5]
                        event_dict['egg_level'] = list(set(level_list))
                if not event_dict.get('event_start'):
                    raid_embed.clear_fields()
                    raid_embed.add_field(name=_('**New Raid Hour Report**'), value=f"Meowth! Next, I'll need to know what **date and time** the event starts. This should be the actual time that the raid hour starts{', I will mute ' + bot_account.mention + ' half an hour before this time' if bot_account else ''}. Reply with a date and time. You can reply with **cancel** to stop anytime.", inline=False)
                    event_start_wait = await channel.send(embed=raid_embed)
                    try:
                        event_start_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        event_start_msg = None
                    await utils.safe_delete(event_start_wait)
                    if not event_start_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(event_start_msg)
                    if event_start_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    else:
                        try:
                            event_start = dateparser.parse(event_start_msg.content)
                            event_start = event_start - datetime.timedelta(hours=self.bot.guild_dict[channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
                            event_dict['event_start'] = event_start
                            event_dict['mute_time'] = event_start - datetime.timedelta(minutes=30)
                            event_dict['channel_time'] = event_start - datetime.timedelta(hours=3)
                            if datetime.datetime.utcnow() > event_start:
                                raid_embed.clear_fields()
                                raid_embed.add_field(name=_('**New Raid Hour Report**'), value=f"Meowth! I need a time in the future! Retry or reply with **cancel**.", inline=False)
                                event_start_wait = await channel.send(embed=raid_embed, delete_after=20)
                                event_dict['event_start'] = None
                                continue
                        except:
                            raid_embed.clear_fields()
                            raid_embed.add_field(name=_('**New Raid Hour Report**'), value=f"Meowth! I couldn't understand your time! Retry or reply with **cancel**.", inline=False)
                            event_start_wait = await channel.send(embed=raid_embed, delete_after=20)
                            continue
                if not event_dict.get('event_end'):
                    raid_embed.clear_fields()
                    raid_embed.add_field(name=_('**New Raid Hour Report**'), value=f"Meowth! Next, I'll need to know what **date and time** the event ends. This should be the actual time that the raid hour ends{', I will unmute ' + bot_account.mention + ' at this time' if bot_account else ''}. Reply with a date and time. You can reply with **cancel** to stop anytime.", inline=False)
                    event_end_wait = await channel.send(embed=raid_embed)
                    try:
                        event_end_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        event_end_msg = None
                    await utils.safe_delete(event_end_wait)
                    if not event_end_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(event_end_msg)
                    if event_end_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    else:
                        try:
                            event_end = dateparser.parse(event_end_msg.content)
                            event_end = event_end - datetime.timedelta(hours=self.bot.guild_dict[channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
                            event_dict['event_end'] = event_end
                            if event_start > event_end:
                                raid_embed.clear_fields()
                                raid_embed.add_field(name=_('**New Raid Hour Report**'), value=f"Meowth! The end time has to be after the start time! Retry or reply with **cancel**.", inline=False)
                                event_start_wait = await channel.send(embed=raid_embed, delete_after=20)
                                event_dict['event_end'] = None
                                continue
                        except:
                            raid_embed.clear_fields()
                            raid_embed.add_field(name=_('**New Raid Hour Report**'), value=f"Meowth! I couldn't understand your time! Retry or reply with **cancel**.", inline=False)
                            event_end_wait = await channel.send(embed=raid_embed, delete_after=20)
                            continue
                if event_dict.get('make_trains') == None:
                    raid_embed.clear_fields()
                    raid_embed.add_field(name=_('**New Raid Hour Report**'), value=f"Meowth! Now, would you like some channels to go with this event for coordination? I'll help you make some channels automatically three hours before the scheduled event.\nReply with **train** and I'll make train channels, usable for raids.\nReply with **meetup** and I'll make meetup channels for other events.\nReply with **none** to skip making channels.\nYou can reply with **cancel** to stop anytime.", inline=False)
                    make_trains_wait = await channel.send(embed=raid_embed)
                    try:
                        make_trains_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        make_trains_msg = None
                    await utils.safe_delete(make_trains_wait)
                    if not make_trains_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(make_trains_msg)
                    if make_trains_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif make_trains_msg.clean_content.lower() == "train":
                        event_dict['make_trains'] = True
                        event_dict['make_meetups'] = False
                    elif make_trains_msg.clean_content.lower() == "meetup":
                        event_dict['channel_time'] = event_start - datetime.timedelta(days=3)
                        event_dict['make_trains'] = False
                        event_dict['make_meetups'] = True
                    elif make_trains_msg.clean_content.lower() == "none":
                        event_dict['make_trains'] = False
                        event_dict['make_meetups'] = False
                    else:
                        raid_embed.clear_fields()
                        raid_embed.add_field(name=_('**New Raid Hour Report**'), value=f"Meowth! I couldn't understand your response! Retry or reply with **cancel**.", inline=False)
                        make_trains_wait = await channel.send(embed=raid_embed, delete_after=20)
                        continue
                if event_dict['make_trains'] or event_dict['make_meetups']:
                    if not event_dict.get('train_channel'):
                        raid_embed.clear_fields()
                        raid_embed.add_field(name=_('**New Raid Hour Report**'), value=f"Meowth! Now, what **channel** would you like the channels to be reported in? Reply with a #mention, ID, or case-sensitive name of the channel. You can reply with **cancel** to stop anytime.", inline=False)
                        train_channel_wait = await channel.send(embed=raid_embed)
                        try:
                            train_channel_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            train_channel_msg = None
                        await utils.safe_delete(train_channel_wait)
                        if not train_channel_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(train_channel_msg)
                        if train_channel_msg.clean_content.lower() == "cancel":
                            error = _("cancelled the report")
                            break
                        else:
                            converter = commands.TextChannelConverter()
                            try:
                                train_channel = await converter.convert(ctx, train_channel_msg.content)
                                event_dict['train_channel'] = train_channel.id
                            except:
                                raid_embed.clear_fields()
                                raid_embed.add_field(name=_('**New Raid Hour Report**'), value=f"Meowth! I couldn't find that channel! Retry or reply with **cancel**.", inline=False)
                                bot_channel_wait = await channel.send(embed=raid_embed, delete_after=20)
                                continue
                    if not event_dict.get('event_title'):
                        raid_embed.clear_fields()
                        raid_embed.add_field(name=_('**New Raid Hour Report**'), value=f"Meowth! Now, reply with the **event title** for your channels. This can be something like `Legendary Raid Hour`, `Community Day` etc. You can reply with **cancel** to stop anytime.", inline=False)
                        event_title_wait = await channel.send(embed=raid_embed)
                        try:
                            event_title_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            event_title_msg = None
                        await utils.safe_delete(event_title_wait)
                        if not event_title_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(event_title_msg)
                        if event_title_msg.clean_content.lower() == "cancel":
                            error = _("cancelled the report")
                            break
                        else:
                            event_dict['event_title'] = event_title_msg.clean_content.lower()
                    if not event_dict.get('event_locations'):
                        raid_embed.clear_fields()
                        raid_embed.add_field(name=_('**New Raid Hour Report**'), value=f"Meowth! Now, reply with a comma separated list of the **event locations** for your channels. I'll make a channel for each location. You can reply with **cancel** to stop anytime.", inline=False)
                        event_loc_wait = await channel.send(embed=raid_embed)
                        try:
                            event_loc_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            event_loc_msg = None
                        await utils.safe_delete(event_loc_wait)
                        if not event_loc_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(event_loc_msg)
                        if event_loc_msg.clean_content.lower() == "cancel":
                            error = _("cancelled the report")
                            break
                        else:
                            event_locations = event_loc_msg.clean_content.split(',')
                            event_locations = [x.strip() for x in event_locations]
                            event_dict['event_locations'] = event_locations
                if ctx.invoked_with == "commday":
                    raid_embed.clear_fields()
                    raid_embed.add_field(name=_('**New Raid Hour Report**'), value=_("Meowth! Since this is a community day, would you like to add **pokemon** to my wild filter to not flood report channels? Note: This will only block reports without IV and without level. Reply with **no** or a **pokemon**. You can reply with **cancel** to stop anytime."), inline=False)
                    bot_account_wait = await channel.send(embed=raid_embed)
                    try:
                        bot_account_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        bot_account_msg = None
                    await utils.safe_delete(bot_account_wait)
                    if not bot_account_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(bot_account_msg)
                    if bot_account_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif bot_account_msg.clean_content.lower() == "no":
                        break
                    else:
                        reply_pokemon = bot_account_msg.clean_content.lower().split(',')
                        reply_pokemon = [x.strip() for x in reply_pokemon]
                        reply_pokemon = [await pkmn_class.Pokemon.async_get_pokemon(self.bot, x, allow_digits=True) for x in reply_pokemon]
                        reply_pokemon = [x for x in reply_pokemon if x]
                        string_list = []
                        for pokemon in reply_pokemon:
                            if not pokemon.form and not pokemon.region and not pokemon.size and not pokemon.gender and not pokemon.shadow:
                                event_dict['event_pokemon'].append(pokemon.id)
                                string_list.append(f"{pokemon.name} (all forms)")
                            else:
                                event_dict['event_pokemon'].append(str(pokemon))
                                string_list.append(str(pokemon))
                        event_dict['event_pokemon_str'] = ', '.join(string_list)
                if ctx.invoked_with == "raidhour" and event_dict.get('recur_weekly') == None:
                    local_start = event_dict['event_start'] + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
                    raid_embed.clear_fields()
                    raid_embed.add_field(name=_('**New Raid Hour Report**'), value=f"Meowth! Since this is a raid hour event, would you like to have this event recur weekly on **{local_start.strftime('%As at %I:%M %p')}** until the event is canceled? You can also skip weeks using **{ctx.prefix}raidhour cancel**. Reply with **yes** or **no**. You can reply with **cancel** to stop anytime.", inline=False)
                    bot_account_wait = await channel.send(embed=raid_embed)
                    try:
                        bot_account_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        bot_account_msg = None
                    await utils.safe_delete(bot_account_wait)
                    if not bot_account_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(bot_account_msg)
                    if bot_account_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif bot_account_msg.clean_content.lower() == "yes":
                        event_dict['recur_weekly'] = True
                    elif bot_account_msg.clean_content.lower() == "no":
                        event_dict['recur_weekly'] = False
                    else:
                        continue
            break
        raid_embed.clear_fields()
        if not error:
            event_dict['egg_level'] = [0] if event_dict['egg_level'] == None else event_dict['egg_level']
            local_start = event_dict['event_start'] + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
            local_end = event_dict['event_end'] + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
            local_mute = event_dict['mute_time'] + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
            local_channel = event_dict['channel_time'] + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
            success_str = f"The event is scheduled to start on {local_start.strftime('%B %d at %I:%M %p')} and end on {local_end.strftime('%B %d at %I:%M %p')}.\n\n"
            if bot_account:
                success_str += f"I will mute {'all raids' if event_dict.get('egg_level', [0]) == [0] else ''}{'raid levels '+', '.join([str(x) for x in event_dict.get('egg_level')]) if event_dict.get('egg_level', [0]) != [0] else ''} from {bot_account.mention} in {bot_channel.mention} on {local_mute.strftime('%B %d at %I:%M %p')} and will unmute at the end of the event.\n\n"
            if event_dict['make_trains']:
                success_str += f"I will make {len(event_dict['event_locations'])} channels in {train_channel.mention} on {local_channel.strftime('%B %d at %I:%M %p')} and remove them at the end of the event. These channels will be for: {(', ').join(event_dict['event_locations'])}. The title for the trains will be: {event_dict['event_title']}.\n\n"
            if event_dict['event_pokemon']:
                success_str += f"I will mute **{event_dict['event_pokemon_str']}** during the event.\n\n"
            if event_dict['recur_weekly']:
                success_str += f"I will make this event every **{local_start.strftime('%As at %I:%M %p')}**.\n\n"
            success_str += f"If this message is deleted the event will be cancelled."
            raid_embed.add_field(name=_('**Raid Hour Report**'), value=f"Meowth! A raid hour has been successfully scheduled. To cancel an event use **{ctx.prefix}raidhour cancel**\n\n{success_str}", inline=False)
            raid_hour_var = self.bot.guild_dict[ctx.guild.id].setdefault('raidhour_dict', {})
            confirmation = await channel.send(embed=raid_embed)
            event_dict['event_start'] = event_dict['event_start'].replace(tzinfo=datetime.timezone.utc).timestamp()
            event_dict['event_end'] = event_dict['event_end'].replace(tzinfo=datetime.timezone.utc).timestamp()
            event_dict['mute_time'] = event_dict['mute_time'].replace(tzinfo=datetime.timezone.utc).timestamp()
            event_dict['channel_time'] = event_dict['channel_time'].replace(tzinfo=datetime.timezone.utc).timestamp()
            self.bot.guild_dict[ctx.guild.id]['raidhour_dict'][confirmation.id] = copy.deepcopy(event_dict)
        else:
            raid_embed.add_field(name=_('**Raid Hour Report Cancelled**'), value=_("Meowth! Your raid hour has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await channel.send(embed=raid_embed, delete_after=10)

    @raidhour.command(name="cancel", aliases=["list"])
    @checks.is_mod()
    async def raidhour_cancel(self, ctx):
        cancel_str = ""
        if not list(self.bot.guild_dict[ctx.guild.id].get('raidhour_dict').keys()):
            return await ctx.send("There are no scheduled raid hours.", delete_after=15)
        index = 1
        for event in list(self.bot.guild_dict[ctx.guild.id].get('raidhour_dict').keys()):
            cancel_str += f"{index}. ID: {str(event)}\n"
            local_start = datetime.datetime.utcfromtimestamp(self.bot.guild_dict[ctx.guild.id].get('raidhour_dict')[event]['event_start']) + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
            local_end = datetime.datetime.utcfromtimestamp(self.bot.guild_dict[ctx.guild.id].get('raidhour_dict')[event]['event_end']) + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
            bot_account = ctx.guild.get_member(self.bot.guild_dict[ctx.guild.id].get('raidhour_dict')[event]['bot_account'])
            bot_channel = self.bot.get_channel(self.bot.guild_dict[ctx.guild.id].get('raidhour_dict')[event]['bot_channel'])
            report_channel = self.bot.get_channel(self.bot.guild_dict[ctx.guild.id].get('raidhour_dict')[event]['train_channel'])
            event_recurs = self.bot.guild_dict[ctx.guild.id].get('raidhour_dict')[event].get('recur_weekly', False)
            if self.bot.guild_dict[ctx.guild.id].get('raidhour_dict')[event]['make_trains']:
                channel_type = "train "
            elif self.bot.guild_dict[ctx.guild.id].get('raidhour_dict')[event]['make_meetups']:
                channel_type = "meetup "
            else:
                channel_type = ""
            if self.bot.guild_dict[ctx.guild.id].get('raidhour_dict')[event]['event_title']:
                cancel_str += f"-- Title: {self.bot.guild_dict[ctx.guild.id].get('raidhour_dict')[event]['event_title']}\n"
            cancel_str += f"-- Event Start: {local_start.strftime('%B %d at %I:%M %p')}\n"
            cancel_str += f"-- Event End: {local_end.strftime('%B %d at %I:%M %p')}\n"
            if bot_account:
                cancel_str += f"-- Muting: {bot_account.mention} {'in '+bot_channel.mention if bot_channel else ''}\n"
            if report_channel:
                cancel_str += f"-- {channel_type.title()}Channels: {(', ').join(self.bot.guild_dict[ctx.guild.id].get('raidhour_dict')[event]['event_locations'])} in {report_channel.mention}\n"
            if event_recurs:
                cancel_str += f"-- Recurring Event: {local_start.strftime('%As at %I:%M %p')}\n"
            cancel_str += "\n"
            index += 1
        paginator = commands.Paginator(prefix=None, suffix=None)
        for line in cancel_str.split('\n'):
            paginator.add_line(line.rstrip())
        for p in paginator.pages:
            await ctx.send(p)
        if ctx.invoked_with == "list":
            return
        event_list_wait = await ctx.send(f"{ctx.author.mention} please send the event number or ID of the event you would like to cancel.", delete_after=60)
        def check(reply):
            if reply.author is not ctx.guild.me and reply.channel.id == ctx.channel.id and reply.author == ctx.message.author:
                return True
            else:
                return False
        try:
            event_list_msg = await self.bot.wait_for('message', timeout=60, check=check)
        except asyncio.TimeoutError:
            event_list_msg = None
        await utils.safe_delete(event_list_wait)
        if not event_list_msg:
            return await ctx.send("You took too long to respond.", delete_after=15)
        else:
            await utils.safe_delete(event_list_msg)
        event_reply = event_list_msg.clean_content.lower().strip()
        if event_reply not in [str(x) for x in list(self.bot.guild_dict[ctx.guild.id].get('raidhour_dict').keys())]:
            if event_reply.isdigit() and int(event_reply) < 1000:
                event_reply = list(self.bot.guild_dict[ctx.guild.id]['raidhour_dict'].keys())[int(event_reply)-1]
            else:
                return await ctx.send("You entered an invalid ID or number", delete_after=15)
        remove_event = True
        if self.bot.guild_dict[ctx.guild.id]['raidhour_dict'][int(event_reply)].get('recur_weekly', False):
            event_list_wait = await ctx.send(f"This is a recurring event. Would you like to cancel **this** event or **all** future events? Reply with **this** or **all**.", delete_after=60)
            try:
                event_list_msg = await self.bot.wait_for('message', timeout=60, check=check)
            except asyncio.TimeoutError:
                event_list_msg = None
            await utils.safe_delete(event_list_wait)
            if not event_list_msg:
                return await ctx.send("You took too long to respond.", delete_after=15)
            else:
                await utils.safe_delete(event_list_msg)
            if event_list_msg.clean_content.lower() == "this":
                remove_event = False
                self.bot.guild_dict[ctx.guild.id]['raidhour_dict'][int(event_reply)]['mute_time'] = self.bot.guild_dict[ctx.guild.id]['raidhour_dict'][int(event_reply)]['mute_time'] + 7*24*60*60
                self.bot.guild_dict[ctx.guild.id]['raidhour_dict'][int(event_reply)]['event_start'] = self.bot.guild_dict[ctx.guild.id]['raidhour_dict'][int(event_reply)]['event_start'] + 7*24*60*60
                self.bot.guild_dict[ctx.guild.id]['raidhour_dict'][int(event_reply)]['event_end'] = self.bot.guild_dict[ctx.guild.id]['raidhour_dict'][int(event_reply)]['event_end'] + 7*24*60*60
                self.bot.guild_dict[ctx.guild.id]['raidhour_dict'][int(event_reply)]['channel_time'] = self.bot.guild_dict[ctx.guild.id]['raidhour_dict'][int(event_reply)]['channel_time'] + 7*24*60*60
            elif event_list_msg.clean_content.lower() == "all":
                remove_event = True
        try:
            self.bot.active_raidhours.remove(int(event_reply))
        except:
            pass
        if remove_event:
            try:
                del self.bot.guild_dict[ctx.guild.id]['raidhour_dict'][int(event_reply)]
            except:
                pass
        await ctx.send(f"Raid hour **{event_reply}** canceled.", delete_after=15)

def setup(bot):
    bot.add_cog(Huntr(bot))

def teardown(bot):
    bot.remove_cog(Huntr)
