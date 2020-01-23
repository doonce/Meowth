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
                                    if alarm_dict.get(reportid, {}).get('expedit') == "delete":
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
        if (ctx.author.bot or message.webhook_id or ctx.author.id in self.bot.managers or ctx.author.id == self.bot.owner) and ctx.author != ctx.guild.me and message.content.lower().startswith("!alarm"):
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
            now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
            message.content = message.content.replace("!alarm","").strip()
            await utils.safe_delete(message)
            try:
                report_details = json.loads(message.content)
            except:
                return
            if report_details.get('type', None) == "raid" or report_details.get('type', None) == "egg":
                raid_cog = self.bot.cogs.get('Raid')
                if not raid_cog:
                    logger.error("Raid Cog not loaded")
                    return
                for event in self.bot.guild_dict[ctx.guild.id].setdefault('raidhour_dict', {}):
                    if utcnow >= self.bot.guild_dict[ctx.guild.id]['raidhour_dict'][event]['mute_time'] and self.bot.guild_dict[ctx.guild.id]['raidhour_dict'][event]['event_end'] >= utcnow:
                        if ctx.author.id == self.bot.guild_dict[ctx.guild.id]['raidhour_dict'][event]['bot_account'] and ctx.channel.id == self.bot.guild_dict[ctx.guild.id]['raidhour_dict'][event]['bot_channel']:
                            raidhour = True
                for channelid in self.bot.guild_dict[message.guild.id]['raidchannel_dict']:
                    channel_gps = self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid].get('coordinates', None)
                    channel_address = self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid].get('address', None)
                    channel_level = self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid].get('egg_level', None)
                    channel_type = self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid].get('type', None)
                    channel_meetup = self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid].get('meetup', {})
                    if channel_level == "EX" or channel_meetup:
                        continue
                    if channel_gps == report_details.get('gps', None) or channel_address == report_details.get('gym', None):
                        channel = self.bot.get_channel(channelid)
                        if embed and channel:
                            await channel.send(embed=embed)
                        if channel_type == 'egg':
                            if not utils.get_level(self.bot, report_details.get('pokemon', None)):
                                logger.error(f"{report_details.get('pokemon', None)} not in raid_json")
                                return
                            await raid_cog._eggtoraid(report_details.get('pokemon', None), channel, message.author, moveset=report_details.get('moves', None))
                        raidexp = report_details.get('raidexp')
                        if raidexp and channel:
                            await raid_cog._timerset(channel, raidexp)
                        await raid_cog.set_moveset(ctx, channel, report_details.get('moves', None))
                        return
                if report_details.get('type', None) == "raid":
                    if not self.bot.guild_dict[message.guild.id]['configure_dict'].get('scanners', {}).get('reports', {}).get('raid'):
                        return
                    reporttype = "raid"
                    pokemon = report_details.setdefault('pokemon', None)
                    pkmn_obj = report_details.setdefault('pkmn_obj', pokemon)
                    if not utils.get_level(self.bot, pokemon):
                        logger.error(f"{pokemon} not in raid_json")
                        return
                    coordinates = report_details.setdefault('gps', None)
                    raid_coordinates = report_details.setdefault('coordinates', coordinates)
                    raid_details = report_details.setdefault('gym', None)
                    if not all([pokemon, coordinates, raid_details]):
                        return
                    egg_level = "0"
                    timeout = int(report_details.get('raidexp', 45))*60
                    expiremsg = _('**This {pokemon} raid has expired!**').format(pokemon=pokemon.title())
                    egg_level = utils.get_level(self.bot, pokemon)
                    if egg_level.isdigit() and int(egg_level) in self.bot.guild_dict[message.guild.id]['configure_dict'].get('scanners', {}).get('raidlvls', []):
                        auto_report = True
                    elif egg_level == "EX" and "EX" in self.bot.guild_dict[message.guild.id]['configure_dict'].get('scanners', {}).get('raidlvls', []):
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
                            ctx.raidreport = await message.channel.send(raidmsg, embed=embed)
                            dm_dict = await raid_cog.send_dm_messages(ctx, str(pokemon), raid_details, f"Meowth! {str(pokemon)} raid reported by {message.author.display_name} in {message.channel.mention}! Details: {raid_details}. React in {message.channel.mention} to report this raid!", copy.deepcopy(embed), dm_dict)
                    else:
                        raidmsg = ""
                        ctx.raidreport = ctx.message
                elif report_details.get('type', None) == "egg":
                    if not self.bot.guild_dict[message.guild.id]['configure_dict'].get('scanners', {}).get('reports', {}).get('egg'):
                        return
                    reporttype = "egg"
                    egg_level = report_details.setdefault('level', None)
                    egg_level = report_details.setdefault('egg_level', egg_level)
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
                            ctx.raidreport = await message.channel.send(raidmsg, embed=embed)
                            dm_dict = await raid_cog.send_dm_messages(ctx, str(egg_level), raid_details, f"Meowth! Level {egg_level} raid egg reported by {message.author.display_name} in {message.channel.mention}! Details: {raid_details}. React in {message.channel.mention} to report this raid!", copy.deepcopy(embed), dm_dict)
                    else:
                        raidmsg = ""
                        ctx.raidreport = ctx.message
                self.bot.guild_dict[message.guild.id]['pokealarm_dict'][ctx.raidreport.id] = {
                    "exp":time.time() + timeout,
                    'expedit': {"content":raidmsg.split("React")[0], "embedcontent":expiremsg},
                    "reporttype":reporttype,
                    "report_channel":message.channel.id,
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
                await self.huntr_wild(ctx, report_details)
                return
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
                if not all([pokestop, coordinates, quest, reward]):
                    return
                await self.huntr_research(ctx, report_details)
                return
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
                if not all([pokestop, coordinates, lure_type]):
                    return
                await self.huntr_lure(ctx, report_details)
                return
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
                if not all([pokestop, coordinates]):
                    return
                await self.huntr_invasion(ctx, report_details)
                return
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
        pokemon = await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, f"{gender if gender else ''} {report_details['pokemon']}")
        if pokemon:
            entered_wild = pokemon.name.lower()
            pokemon.shiny = False
        else:
            return
        if pokemon.id in ctx.bot.guild_dict[message.channel.guild.id]['configure_dict'].get('scanners', {}).setdefault('wildfilter', []) or str(pokemon) in ctx.bot.guild_dict[message.channel.guild.id]['configure_dict'].get('scanners', {}).setdefault('wildfilter', []):
            if not report_details.get("iv_percent", '') and not report_details.get("level", ''):
                return
        wild_details = report_details['coordinates']
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
        if iv_percent or iv_percent == 0:
            iv_str = f" - **{iv_percent}IV**"
        else:
            iv_str = ""
        level = str(report_details.get("level", ''))
        cp = str(report_details.get("cp", ''))
        weather = report_details.get("weather", '')
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
        height = report_details.get("height", '')
        weight = report_details.get("weight", '')
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
            nearest_poi = await gym_matching_cog.find_nearest_poi((wild_coordinates.split(",")[0], wild_coordinates.split(",")[1]), message.guild.id)
            nearest_stop = await gym_matching_cog.find_nearest_stop((wild_coordinates.split(",")[0], wild_coordinates.split(",")[1]), message.guild.id)
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
        ctx.wildreportmsg = await message.channel.send(f"Meowth! Wild {str(pokemon).title()} reported by {message.author.mention}!{stop_str}Coordinates: {wild_coordinates}{iv_str}\n\nUse {omw_emoji} if coming, {catch_emoji} if caught, {expire_emoji} if despawned, {info_emoji} to edit details, {report_emoji} to report new, or {list_emoji} to list all wilds!", embed=wild_embed)
        dm_dict = await wild_cog.send_dm_messages(ctx, str(pokemon), str(nearest_stop), iv_percent, level, ctx.wildreportmsg.content.replace(ctx.author.mention, f"{ctx.author.display_name} in {ctx.channel.mention}"), wild_embed.copy(), dm_dict)
        for reaction in reaction_list:
            await asyncio.sleep(0.25)
            await utils.add_reaction(ctx.wildreportmsg, reaction)
        ctx.bot.guild_dict[message.guild.id]['wildreport_dict'][ctx.wildreportmsg.id] = {
            'report_time':time.time(),
            'exp':time.time() + despawn,
            'expedit': {"content":ctx.wildreportmsg.content, "embedcontent":expiremsg},
            'report_message':message.id,
            'report_channel':message.channel.id,
            'report_author':message.author.id,
            'report_guild':message.guild.id,
            'dm_dict':dm_dict,
            'location':wild_details,
            'coordinates':wild_coordinates,
            'url':wild_gmaps_link,
            'pokemon':entered_wild,
            'pkmn_obj':str(pokemon),
            'wild_iv':wild_iv,
            'level':level,
            'cp':cp,
            'gender':gender,
            'size':pokemon.size,
            'weather':pokemon.weather,
            'omw':[]
        }

    async def huntr_raid(self, ctx, report_details, reporter=None, report_user=None, dm_dict=None):
        if not dm_dict:
            dm_dict = {}
        raid_cog = self.bot.cogs.get('Raid')
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
        timestamp = (message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[message.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))).strftime(_('%I:%M %p (%H:%M)'))
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
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
            await message.channel.send(_('Meowth! The Pokemon {pokemon} does not appear in raids!').format(pokemon=pokemon.name.capitalize()), delete_after=10)
            return
        elif utils.get_level(ctx.bot, str(pokemon)) == "EX":
            await message.channel.send(_("Meowth! The Pokemon {pokemon} only appears in EX Raids! Use **!exraid** to report one!").format(pokemon=pokemon.name.capitalize()), delete_after=10)
            return
        level = utils.get_level(ctx.bot, str(pokemon))
        matched_boss = False
        for boss in self.bot.raid_info['raid_eggs'][str(level)]['pokemon']:
            boss = await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, boss)
            if str(boss) == str(pokemon):
                pokemon = boss
                matched_boss = True
                break
        if not matched_boss:
            for boss in self.bot.raid_info['raid_eggs'][str(level)]['pokemon']:
                boss = await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, boss)
                if boss and boss.id == pokemon.id:
                    pokemon = boss
                    break
        weather = ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'].get(message.channel.id, {}).get('weather', None)
        if not weather and raid_coordinates:
            weather = await raid_cog.auto_weather(ctx, raid_coordinates)
        report_details['pkmn_obj'] = str(pokemon)
        report_details['weather'] = weather
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        if gym_matching_cog:
            gym_info, raid_location, gym_url = await gym_matching_cog.get_poi_info(ctx, raid_details, "raid", dupe_check=False, autocorrect=False)
            if gym_url:
                raid_details = raid_location
            else:
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
                    with open(os.path.join('data', 'gym_data.json'), 'r') as fd:
                        data = json.load(fd)
                    add_gym_dict = {}
                    add_gym_dict[raid_details] = {"coordinates":raid_coordinates, "alias":"", "notes":""}
                    data[str(ctx.guild.id)] = {**data[str(ctx.guild.id)], **add_gym_dict}
                    with open(os.path.join('data', 'gym_data.json'), 'w') as fd:
                        json.dump(data, fd, indent=2, separators=(', ', ': '))
                gym_matching_cog.gym_data = gym_matching_cog.init_json()
                gym_matching_cog.stop_data = gym_matching_cog.init_stop_json()
        raid_embed = await raid_cog.make_raid_embed(ctx, report_details, raidexp)
        if not raid_embed:
            return
        raid_channel = await raid_cog.create_raid_channel(ctx, f"{boss.name.lower()}{'-'+boss.region.lower() if boss.region else ''}{'-'+boss.form.lower() if boss.form else ''}", raid_details, "raid")
        if not raid_channel:
            return
        await asyncio.sleep(1)
        ctx.raidreport = await message.channel.send(content=f"Meowth! {str(pokemon).title()} raid reported by {message.author.mention}! Details: {raid_details}. Coordinate in {raid_channel.mention}\n\nUse {maybe_reaction} if interested, {omw_reaction} if coming, {here_reaction} if there, {cancel_reaction} to cancel, {report_emoji} to report new, or {list_emoji} to list all raids!", embed=raid_embed)
        raidmsg = f"Meowth! {str(pokemon).title()} raid reported by {message.author.mention} in {message.channel.mention}! Details: {raid_details}. Coordinate here!\n\nClick the {help_reaction} to get help on commands, {maybe_reaction} if interested, {omw_reaction} if coming, {here_reaction} if there, or {cancel_reaction} to cancel.\n\nThis channel will be deleted five minutes after the timer expires."
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
        ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid_channel.id] = {
            'report_channel':message.channel.id,
            'report_guild':message.guild.id,
            'report_author':message.author.id,
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
        await raid_channel.send(f"This raid was reported by a bot. If it is a duplicate of a raid already reported by a human, I can delete it with three **!duplicate** messages.\nThe weather may be inaccurate for this raid, use **{ctx.prefix}weather** to set the correct weather.")
        ctrs_dict = await raid_cog._get_generic_counters(message.guild, str(pokemon), weather)
        if str(level) in ctx.bot.guild_dict[message.guild.id]['configure_dict'].get('counters', {}).get('auto_levels', []):
            try:
                ctrsmsg = "Here are the best counters for the raid boss in currently known weather conditions! Update weather with **!weather**. If you know the moveset of the boss, you can react to this message with the matching emoji and I will update the counters."
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
        ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid_channel.id]['dm_dict'] = dm_dict
        if report_user:
            raid_reports = self.bot.guild_dict[message.guild.id].setdefault('trainers', {}).setdefault(report_user.id, {}).setdefault('reports', {}).setdefault('raid', 0) + 1
            self.bot.guild_dict[message.guild.id]['trainers'][report_user.id]['reports']['raid'] = raid_reports
        await raid_cog.set_moveset(ctx, raid_channel, moves)
        return raid_channel

    async def huntr_raidegg(self, ctx, report_details, reporter=None, report_user=None, dm_dict=None):
        if not dm_dict:
            dm_dict = {}
        raid_cog = self.bot.cogs.get('Raid')
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
        timestamp = (message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[message.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))).strftime(_('%I:%M %p (%H:%M)'))
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
        egg_level = str(report_details.get('level'))
        raid_details = report_details.get('gym')
        raidexp = report_details.get('raidexp', 60)
        raid_coordinates = report_details['gps']
        report_details['coordinates'] = raid_coordinates
        raid_details = report_details.get('gym', raid_coordinates)
        report_details['address'] = raid_details
        weather = ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'].get(message.channel.id, {}).get('weather', None)
        if not weather and raid_coordinates:
            weather = await raid_cog.auto_weather(ctx, raid_coordinates)
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        if gym_matching_cog:
            gym_info, raid_location, gym_url = await gym_matching_cog.get_poi_info(ctx, raid_details, "raid", dupe_check=False, autocorrect=False)
            if gym_url:
                raid_details = raid_location
            else:
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
                    with open(os.path.join('data', 'gym_data.json'), 'r') as fd:
                        data = json.load(fd)
                    add_gym_dict = {}
                    add_gym_dict[raid_details] = {"coordinates":raid_coordinates, "alias":"", "notes":""}
                    data[str(ctx.guild.id)] = {**data[str(ctx.guild.id)], **add_gym_dict}
                    with open(os.path.join('data', 'gym_data.json'), 'w') as fd:
                        json.dump(data, fd, indent=2, separators=(', ', ': '))
        raid_embed = await raid_cog.make_raid_embed(ctx, report_details, raidexp)
        if not raid_embed:
            return
        raid_channel = await raid_cog.create_raid_channel(ctx, egg_level, raid_details, "egg")
        if not raid_channel:
            return
        await asyncio.sleep(1)
        ctx.raidreport = await message.channel.send(content=f"Meowth! Level {egg_level} raid egg reported by {message.author.mention}! Details: {raid_details}. Coordinate in {raid_channel.mention}\n\nUse {maybe_reaction} if interested, {omw_reaction} if coming, {here_reaction} if there, {cancel_reaction} to cancel, {report_emoji} to report new, or {list_emoji} to list all raids!", embed=raid_embed)
        raidmsg = f"Meowth! Level {egg_level} raid egg reported by {message.author.mention} in {message.channel.mention}! Details: {raid_details}. Coordinate here!\n\nClick the {help_reaction} to get help on commands, {maybe_reaction} if interested, {omw_reaction} if coming, {here_reaction} if there, or {cancel_reaction} to cancel.\n\nThis channel will be deleted five minutes after the timer expires."
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
        ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid_channel.id] = {
            'report_channel':message.channel.id,
            'report_guild':message.guild.id,
            'report_author':message.author.id,
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
        else:
            await raid_channel.send(content=_('Meowth! Hey {member}, if you can, set the time left until the egg hatches using **!timerset <minutes>** so others can check it with **!timer**.').format(member=message.author.mention))
        await raid_channel.send(f"This egg was reported by a bot. If it is a duplicate of a raid already reported by a human, I can delete it with three **!duplicate** messages.\nThe weather may be inaccurate for this raid, use **{ctx.prefix}weather** to set the correct weather.")
        if len(ctx.bot.raid_info['raid_eggs'][egg_level]['pokemon']) == 1:
            pokemon = await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, ctx.bot.raid_info['raid_eggs'][egg_level]['pokemon'][0])
            await raid_cog._eggassume(ctx, str(pokemon), raid_channel)
        elif egg_level == "5" and ctx.bot.guild_dict[raid_channel.guild.id]['configure_dict'].get('settings', {}).get('regional', None) in ctx.bot.raid_list:
            pokemon = await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, ctx.bot.guild_dict[raid_channel.guild.id]['configure_dict']['settings']['regional'])
            await raid_cog._eggassume(ctx, str(pokemon), raid_channel)
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
        channel = message.channel
        author = message.author
        guild = message.guild
        research_cog = self.bot.cogs.get('Research')
        nearest_stop = ""
        location = report_details['pokestop']
        gps = report_details['gps']
        quest = report_details['quest']
        reward = report_details['reward']
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        to_midnight = 24*60*60 - ((timestamp-timestamp.replace(hour=0, minute=0, second=0, microsecond=0)).seconds)
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        stop_info = ""
        if gym_matching_cog:
            stop_info, stop_location, stop_url = await gym_matching_cog.get_poi_info(ctx, location, "research", dupe_check=False, autocorrect=False)
            if stop_url:
                location = stop_location
            else:
                with open(os.path.join('data', 'stop_data.json'), 'r') as fd:
                    data = json.load(fd)
                add_stop_dict = {}
                add_stop_dict[location] = {"coordinates":gps, "alias":"", "notes":""}
                data[str(ctx.guild.id)] = {**data[str(ctx.guild.id)], **add_stop_dict}
                with open(os.path.join('data', 'stop_data.json'), 'w') as fd:
                    json.dump(data, fd, indent=2, separators=(', ', ': '))
                gym_matching_cog.gym_data = gym_matching_cog.init_json()
                gym_matching_cog.stop_data = gym_matching_cog.init_stop_json()
        await research_cog.send_research(ctx, location, quest, reward)

    async def huntr_lure(self, ctx, report_details):
        message = ctx.message
        channel = message.channel
        author = message.author
        guild = message.guild
        lure_cog = self.bot.cogs.get('Lure')
        nearest_stop = ""
        location = report_details['pokestop']
        gps = report_details['gps']
        lure_type = report_details['lure_type'].lower()
        timer = report_details.get('expire', 30)
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        stop_info = ""
        if gym_matching_cog:
            nearest_stop = await gym_matching_cog.find_nearest_stop((gps.split(",")[0],gps.split(",")[1]), guild.id)
            if nearest_stop:
                location = nearest_stop
            stop_info, location, stop_url = await gym_matching_cog.get_poi_info(ctx, location, "lure")
        if not location:
            return
        await lure_cog.send_lure(ctx, lure_type, location, timer)

    async def huntr_invasion(self, ctx, report_details):
        message = ctx.message
        channel = message.channel
        author = message.author
        guild = message.guild
        invasion_cog = self.bot.cogs.get('Invasion')
        nearest_stop = ""
        location = report_details['pokestop']
        gps = report_details['gps']
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
            nearest_stop = await gym_matching_cog.find_nearest_stop((gps.split(",")[0],gps.split(",")[1]), guild.id)
            if nearest_stop:
                location = nearest_stop
            stop_info, location, stop_url = await gym_matching_cog.get_poi_info(ctx, location, "invasion")
        if not location:
            return
        await invasion_cog.send_invasion(ctx, location, reward, gender, leader, timer)

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def huntrraid(self, ctx):
        """Simulates a huntr raid"""
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        await utils.safe_delete(message)
        tier5 = str(ctx.bot.raid_info['raid_eggs']["5"]['pokemon'][0]).lower()
        description = f"**Marilla Park.**\n{tier5}\n**CP:** 60540 - **Moves:** Confusion / Shadow Ball\n*Raid Ending: 0 hours 10 min 50 sec*"
        url = "https://gymhuntr.com/#34.008618,-118.49125"
        img_url = 'https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/pkmn/150_.png?cache=1'
        huntrembed = discord.Embed(title=_('Level 5 Raid has started!'), description=description, url=url, colour=message.guild.me.colour)
        huntrembed.set_thumbnail(url=img_url)
        huntrmessage = await ctx.channel.send(embed=huntrembed)
        ctx = await self.bot.get_context(huntrmessage)
        await self.on_huntr(ctx)

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def huntregg(self, ctx):
        """Simulates a huntr raid egg"""
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        await utils.safe_delete(message)
        description = "**Marilla Park.**\n*Raid Starting: 0 hours 46 min 50 sec*"
        url = "https://gymhuntr.com/#34.008618,-118.49125"
        img_url = 'https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/eggs/5.png?cache=1'
        huntrembed = discord.Embed(title=_('Level 5 Raid is starting soon!!'), description=description, url=url, colour=message.guild.me.colour)
        huntrembed.set_thumbnail(url=img_url)
        huntrmessage = await ctx.channel.send(embed=huntrembed)
        ctx = await self.bot.get_context(huntrmessage)
        await self.on_huntr(ctx)

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def huntrwild(self, ctx):
        """Simulates a huntr wild"""
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        await utils.safe_delete(message)
        description = "Click above to view the wild\n\n*Remaining: 25 min 3 sec*\nWeather: *None*"
        url = "https://gymhuntr.com/#34.008618,-118.49125"
        img_url = 'https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/pkmn/150_.png?cache=1'
        huntrembed = discord.Embed(title=_('A wild Mewtwo (150) has appeared!'), description=description, url=url, colour=message.guild.me.colour)
        huntrembed.set_thumbnail(url=img_url)
        huntrmessage = await ctx.channel.send(embed=huntrembed)
        ctx = await self.bot.get_context(huntrmessage)
        await self.on_huntr(ctx)

    @commands.command()
    async def alarmrecover(self, ctx):
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

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def alarmraid(self, ctx):
        """Simulates an alarm raid"""
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        await utils.safe_delete(message)
        random_raid = random.choice(ctx.bot.raid_info['raid_eggs']["5"]['pokemon'])
        pokemon = await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, random_raid)
        embed = discord.Embed(title="Title", description="Embed Description")
        huntrmessage = await ctx.channel.send('!alarm ' + str({"type":"raid", "pokemon":random_raid.lower(), "gym":"Marilla Park", "gps":"39.628941,-79.935063", "moves":f"{pokemon.quick_moves[0].title()} / {pokemon.charge_moves[0].title()}", "raidexp":10}).replace("'", '"'), embed=embed)
        ctx = await self.bot.get_context(huntrmessage)
        await self.on_pokealarm(ctx)

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def alarmegg(self, ctx):
        """Simulates an alarm raid egg"""
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        await utils.safe_delete(message)
        embed = discord.Embed(title="Title", description="Embed Description")
        huntrmessage = await ctx.channel.send('!alarm {"type":"egg", "level":"5", "gym":"Marilla Park", "gps":"39.628941,-79.935063"}', embed=embed)
        ctx = await self.bot.get_context(huntrmessage)
        await self.on_pokealarm(ctx)

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def alarmwild(self, ctx):
        """Simulates an alarm wild"""
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        await utils.safe_delete(message)
        huntrmessage = await ctx.channel.send('!alarm {"type":"wild", "pokemon":"Ditto", "gps":"39.645742,-79.96908", "expire":"5 min 0 sec", "iv_percent":"95.5", "iv_long":"14 / 14/ 15", "level":"27", "gender":"male", "height":"0.4", "weight":"6", "moveset":"Quick Attack / Wild Charge", "disguise":"Yanma"}')
        ctx = await self.bot.get_context(huntrmessage)
        await self.on_pokealarm(ctx)

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def alarmquest(self, ctx):
        """Simulates an alarm quest"""
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        await utils.safe_delete(message)
        huntrmessage = await ctx.channel.send('!alarm {"type":"research", "pokestop":"Disney Park", "gps":"39.645742,-79.96908", "quest":"Catch 5 Electric Pokemon", "reward":"Pikachu Encounter"}')
        ctx = await self.bot.get_context(huntrmessage)
        await self.on_pokealarm(ctx)

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def alarmlure(self, ctx):
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

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def alarminv(self, ctx):
        """Simulates an alarm invasion"""
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        await utils.safe_delete(message)
        random_type = random.choice(self.bot.type_list)
        huntrmessage = await ctx.channel.send('!alarm ' + str({"type":"invasion", "pokestop":"Marilla Park", "reward":['snorlax'], "gps":"39.645742,-79.96908", "gender":"female", "expire":25}).replace("'", '"'))
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
                return
            bot_account = guild.get_member(event_dict['bot_account'])
            bot_channel = self.bot.get_channel(event_dict['bot_channel'])
            while True:
                now = datetime.datetime.utcnow()
                wait_time = [600]
                event_dict = copy.deepcopy(self.bot.guild_dict[guild.id]['raidhour_dict'][event_id])
                if event_dict['make_trains'] or event_dict.get('make_meetups'):
                    if now >= event_dict['channel_time']:
                        event_start = event_dict['event_start'] + datetime.timedelta(hours=self.bot.guild_dict[guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
                        event_end = event_dict['event_end'] + datetime.timedelta(hours=self.bot.guild_dict[guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
                        train_channel = self.bot.get_channel(event_dict['train_channel'])
                        for location in event_dict['event_locations']:
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
                        self.bot.guild_dict[guild.id]['raidhour_dict'][event_id]['make_trains'] = False
                        self.bot.guild_dict[guild.id]['raidhour_dict'][event_id]['make_meetups'] = False
                    else:
                        wait_time.append((event_dict['channel_time'] - now).total_seconds())
                if event_dict.get('event_pokemon'):
                    if event_dict['event_pokemon'] not in self.bot.guild_dict[guild.id]['configure_dict']['scanners']['wildfilter']:
                        self.bot.guild_dict[guild.id]['configure_dict']['scanners']['wildfilter'].append(event_dict['event_pokemon'])
                if bot_account:
                    if now < event_dict['mute_time']:
                        wait_time.append((event_dict['mute_time'] - now).total_seconds())
                if now >= event_dict['event_end']:
                    try:
                        user_message = await report_channel.fetch_message(event_dict['user_message'])
                        await utils.safe_delete(user_message)
                    except:
                        pass
                    try:
                        self.bot.guild_dict[guild.id]['configure_dict']['scanners']['wildfilter'].remove(event_dict['event_pokemon'])
                    except:
                        pass
                    try:
                        del self.bot.guild_dict[guild.id]['raidhour_dict'][event_id]
                    except:
                        pass
                    try:
                        self.bot.active_raidhours.remove(event_id)
                    except:
                        pass
                    return
                else:
                    wait_time.append((event_dict['event_end'] - now).total_seconds())
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
            "event_pokemon":None,
            "event_pokemon_str":None
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
                    raid_embed.add_field(name=_('**New Raid Hour Report**'), value=_("Meowth! Since this is a community day, would you like to add a pokemon to my wild filter to not flood report channels? Reply with **no** or a pokemon. You can reply with **cancel** to stop anytime."), inline=False)
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
                        pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, bot_account_msg.clean_content.lower())
                        if pokemon:
                            if not pokemon.form and not pokemon.region and not pokemon.size and not pokemon.gender and not pokemon.shadow:
                                event_dict['event_pokemon'] = pokemon.id
                                event_dict['event_pokemon_str'] = f"{pokemon.name} (all forms)"
                            else:
                                event_dict['event_pokemon'] = str(pokemon)
                                event_dict['event_pokemon_str'] = str(pokemon)
            break
        raid_embed.clear_fields()
        if not error:
            local_start = event_dict['event_start'] + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
            local_end = event_dict['event_end'] + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
            local_mute = event_dict['mute_time'] + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
            local_channel = event_dict['channel_time'] + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
            success_str = f"The event is scheduled to start on {local_start.strftime('%B %d at %I:%M %p')} and end on {local_end.strftime('%B %d at %I:%M %p')}.\n\n"
            if bot_account:
                success_str += f"I will mute {bot_account.mention} in {bot_channel.mention} on {local_mute.strftime('%B %d at %I:%M %p')} and will unmute at the end of the event.\n\n"
            if event_dict['make_trains']:
                success_str += f"I will make {len(event_dict['event_locations'])} channels in {train_channel.mention} on {local_channel.strftime('%B %d at %I:%M %p')} and remove them at the end of the event. These channels will be for: {(', ').join(event_dict['event_locations'])}. The title for the trains will be: {event_dict['event_title']}."
            if event_dict['event_pokemon']:
                success_str += f"I will mute **{event_dict['event_pokemon_str']}** during the event."
            raid_embed.add_field(name=_('**Raid Hour Report**'), value=f"Meowth! A raid hour has been successfully scheduled. To cancel an event use **{ctx.prefix}raidhour cancel**\n\n{success_str}", inline=False)
            raid_hour_var = self.bot.guild_dict[ctx.guild.id].setdefault('raidhour_dict', {})
            self.bot.guild_dict[ctx.guild.id]['raidhour_dict'][ctx.message.id] = copy.deepcopy(event_dict)
            confirmation = await channel.send(embed=raid_embed)
        else:
            raid_embed.add_field(name=_('**Raid Hour Report Cancelled**'), value=_("Meowth! Your raid hour has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await channel.send(embed=raid_embed, delete_after=10)

    @raidhour.command(name="cancel", aliases=["list"])
    @checks.is_mod()
    async def raidhour_cancel(self, ctx):
        cancel_str = ""
        if not list(self.bot.guild_dict[ctx.guild.id].get('raidhour_dict').keys()):
            return await ctx.send("There are no scheduled raid hours.", delete_after=15)
        for event in list(self.bot.guild_dict[ctx.guild.id].get('raidhour_dict').keys()):
            cancel_str += f"ID: **{str(event)}**\n"
            local_start = self.bot.guild_dict[ctx.guild.id].get('raidhour_dict')[event]['event_start'] + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
            local_end = self.bot.guild_dict[ctx.guild.id].get('raidhour_dict')[event]['event_end'] + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
            bot_account = ctx.guild.get_member(self.bot.guild_dict[ctx.guild.id].get('raidhour_dict')[event]['bot_account'])
            bot_channel = self.bot.get_channel(self.bot.guild_dict[ctx.guild.id].get('raidhour_dict')[event]['bot_channel'])
            report_channel = self.bot.get_channel(self.bot.guild_dict[ctx.guild.id].get('raidhour_dict')[event]['train_channel'])
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
            cancel_str += "\n"
        if ctx.invoked_with == "list":
            await ctx.send(cancel_str)
            return
        event_list_wait = await ctx.send(f"{ctx.author.mention} please send the event ID of the event you would like to cancel.\n{cancel_str}", delete_after=60)
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
            return await ctx.send("You entered an invalid ID", delete_after=15)
        try:
            self.bot.active_raidhours.remove(int(event_reply))
        except:
            pass
        bot_account = ctx.guild.get_member(self.bot.guild_dict[ctx.guild.id]['raidhour_dict'][int(event_reply)]['bot_account'])
        bot_channel = self.bot.get_channel(self.bot.guild_dict[ctx.guild.id]['raidhour_dict'][int(event_reply)]['bot_channel'])
        try:
            del self.bot.guild_dict[ctx.guild.id]['raidhour_dict'][int(event_reply)]
        except:
            pass
        await ctx.send(f"Raid hour canceled.", delete_after=15)

def setup(bot):
    bot.add_cog(Huntr(bot))

def teardown(bot):
    bot.remove_cog(Huntr)
