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
import json
import random
import functools

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
        self.event_loop = asyncio.get_event_loop()

    def cog_unload(self):
        self.huntr_cleanup.cancel()

    @tasks.loop(seconds=600)
    async def huntr_cleanup(self, loop=True):
        logger.info('------ BEGIN ------')
        for guild in list(self.bot.guilds):
            report_edit_dict = {}
            report_delete_dict = {}
            pokealarm_dict = self.bot.guild_dict[guild.id].get('pokealarm_dict', {})
            pokehuntr_dict = self.bot.guild_dict[guild.id].get('pokehuntr_dict', {})
            report_dict_dict = {
                'pokealarm_dict':pokealarm_dict,
                'pokehuntr_dict':pokehuntr_dict
            }
            for report_dict in list(report_dict_dict.keys()):
                for reportid in list(report_dict_dict.get(report_dict, {}).keys()):
                    if report_dict_dict.get(report_dict, {}).get(reportid, {}).get('exp', 0) <= time.time():
                        report_channel = self.bot.get_channel(report_dict_dict.get(report_dict, {}).get(reportid, {}).get('report_channel'))
                        if report_channel:
                            user_report = report_dict_dict.get(report_dict, {}).get(reportid, {}).get('report_message', None)
                            if user_report:
                                report_delete_dict[user_report] = {"action":"delete", "channel":report_channel}
                            if report_dict_dict.get(report_dict, {}).get(reportid, {}).get('expedit') == "delete":
                                report_delete_dict[reportid] = {"action":"delete", "channel":report_channel}
                            else:
                                report_edit_dict[reportid] = {"action":report_dict_dict.get(report_dict, {}).get(reportid, {}).get('expedit', ''), "channel":report_channel}
                            if report_dict_dict.get(report_dict, {}).get(reportid, {}).get('dm_dict', False):
                                self.bot.loop.create_task(utils.expire_dm_reports(self.bot, report_dict_dict.get(report_dict, {}).get(reportid, {}).get('dm_dict', {})))
                        try:
                            del self.bot.guild_dict[guild.id][report_dict][reportid]
                        except KeyError:
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
                        colour = report_meetup.embeds[0].colour.value
                    await report_message.edit(content=report_edit_dict[messageid]['action']['content'], embed=discord.Embed(description=report_edit_dict[messageid]['action'].get('embedcontent'), colour=colour))
                    await report_message.clear_reactions()
                except:
                    pass
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
        if not ctx.guild:
            return
        if (ctx.author.bot or message.webhook_id or ctx.author.id in self.bot.managers or ctx.author.id == self.bot.owner) and ctx.author != ctx.guild.me and message.content.lower().startswith("!alarm"):
            await self.on_pokealarm(ctx)
        if (str(ctx.author) == 'GymHuntrBot#7279') or (str(ctx.author) == 'HuntrBot#1845'):
            await self.on_huntr(ctx)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        channel = self.bot.get_channel(payload.channel_id)
        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.errors.NotFound, AttributeError, discord.Forbidden):
            return
        guild = message.guild
        try:
            user = guild.get_member(payload.user_id)
        except AttributeError:
            return
        if user == self.bot.user:
            return
        ctx = await self.bot.get_context(message)
        pokealarm_dict = copy.deepcopy(ctx.bot.guild_dict[channel.guild.id].get('pokealarm_dict', {}))
        pokehuntr_dict = copy.deepcopy(ctx.bot.guild_dict[channel.guild.id].get('pokehuntr_dict', {}))
        raid_cog = self.bot.cogs.get('Raid')
        if message.id in pokealarm_dict.keys() and not user.bot:
            if str(payload.emoji) == self.bot.custom_emoji.get('huntr_report', '\u2705'):
                await self.on_pokealarm(ctx, user)
            elif str(payload.emoji) == self.bot.custom_emoji.get('raid_maybe', '\u2753'):
                raid_channel = await self.on_pokealarm(ctx, user)
                ctx.message.author, ctx.author = user, user
                ctx.channel, ctx.message.channel = raid_channel, raid_channel
                await raid_cog._rsvp(ctx, "maybe", "1")
            elif str(payload.emoji) == self.bot.custom_emoji.get('raid_omw', '\ud83c\udfce'):
                raid_channel = await self.on_pokealarm(ctx, user)
                ctx.message.author, ctx.author = user, user
                ctx.channel, ctx.message.channel = raid_channel, raid_channel
                await raid_cog._rsvp(ctx, "coming", "1")
            elif str(payload.emoji) == self.bot.custom_emoji.get('raid_here', '\U0001F4CD'):
                raid_channel = await self.on_pokealarm(ctx, user)
                ctx.message.author, ctx.author = user, user
                ctx.channel, ctx.message.channel = raid_channel, raid_channel
                await raid_cog._rsvp(ctx, "here", "1")
        elif message.id in pokehuntr_dict.keys() and not user.bot:
            if str(payload.emoji) == self.bot.custom_emoji.get('huntr_report', '\u2705'):
                await self.on_huntr(ctx, user)
            elif str(payload.emoji) == self.bot.custom_emoji.get('raid_maybe', '\u2753'):
                raid_channel = await self.on_huntr(ctx, user)
                ctx.message.author, ctx.author = user, user
                ctx.channel, ctx.message.channel = raid_channel, raid_channel
                await raid_cog._rsvp(ctx, "maybe", "1")
            elif str(payload.emoji) == self.bot.custom_emoji.get('raid_omw', '\ud83c\udfce'):
                raid_channel = await self.on_huntr(ctx, user)
                ctx.message.author, ctx.author = user, user
                ctx.channel, ctx.message.channel = raid_channel, raid_channel
                await raid_cog._rsvp(ctx, "coming", "1")
            elif str(payload.emoji) == self.bot.custom_emoji.get('raid_here', '\U0001F4CD'):
                raid_channel = await self.on_huntr(ctx, user)
                ctx.message.author, ctx.author = user, user
                ctx.channel, ctx.message.channel = raid_channel, raid_channel
                await raid_cog._rsvp(ctx, "here", "1")

    async def on_huntr(self, ctx, reactuser=None):
        message = ctx.message
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])).strftime('%I:%M %p')
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])
        auto_raid = self.bot.guild_dict[message.guild.id]['configure_dict']['scanners']['reports'].get('raid', False)
        auto_egg = self.bot.guild_dict[message.guild.id]['configure_dict']['scanners']['reports'].get('egg', False)
        auto_wild = self.bot.guild_dict[message.guild.id]['configure_dict']['scanners']['reports'].get('wild', False)
        raid_channel = None
        maybe_reaction = self.bot.custom_emoji.get('raid_maybe', '\u2753')
        omw_reaction = self.bot.custom_emoji.get('raid_omw', '\ud83c\udfce')
        here_reaction = self.bot.custom_emoji.get('raid_here', '\U0001F4CD')
        react_list = [maybe_reaction, omw_reaction, here_reaction]
        if not auto_raid and not auto_egg and not auto_wild:
            return
        if not reactuser:
            #get gps
            if message.embeds and (message.author.id == 329412230481444886 or message.author.id == 295116861920772098 or message.author.id == message.guild.me.id):
                raid_cog = self.bot.cogs.get('Raid')
                if not raid_cog:
                    logger.error("Raid Cog not loaded")
                    return
                huntrgps = ""
                try:
                    huntrgps = message.embeds[0].url.split('#')[1]
                except IndexError:
                    req = urllib.request.Request(message.embeds[0].url, headers={'User-Agent': 'Magic Browser'})
                    con = urllib.request.urlopen(req)
                    try:
                        huntrgps = con.geturl().split('#')[1]
                        con.close()
                    except IndexError:
                        source = str(con.read().decode('utf8').replace('\n', '').replace(' ', ''))
                        sourceindex = source.find('huntr.com/#')
                        newsourceindex = source.rfind('http', 0, sourceindex)
                        newsourceend = source.find('"', newsourceindex)
                        newsource = source[newsourceindex:newsourceend]
                        huntrgps = newsource.split('#')[1]
                        con.close()
                if not huntrgps:
                    return
            if (message.author.id == 329412230481444886 or message.author.id == message.guild.me.id) and message.embeds:
                if (len(message.embeds[0].title.split(' ')) == 5) and auto_raid:
                    match = re.search('[* ]*([a-zA-Z ]*)[* .]*\n(.*)\n[* CP:]*([0-9]*)[ \-*Moves:]*(.*)\n[*a-zA-Z: ]*([0-2])[ a-z]*([0-9]*)[ a-z]*([0-9]*)', message.embeds[0].description)
                    reporttype = "raid"
                    raid_details = match.group(1).strip()
                    entered_raid = match.group(2).lower()
                    moveset = match.group(4)
                    raidexp = match.group(6)
                    egg_level = 0
                    await utils.safe_delete(message)
                    auto_report = True if int(utils.get_level(self.bot, entered_raid)) in self.bot.guild_dict[message.guild.id]['configure_dict']['scanners']['raidlvls'] else False
                elif (len(message.embeds[0].title.split(' ')) == 6) and auto_egg:
                    match = re.search('[* ]*([a-zA-Z ]*)[* .]*\n[*:a-zA-Z ]*([0-2]*)[ a-z]*([0-9]*)[ a-z]*([0-9]*)', message.embeds[0].description)
                    reporttype = "egg"
                    egg_level = message.embeds[0].title.split(' ')[1]
                    raid_details = match.group(1).strip()
                    raidexp = match.group(3)
                    entered_raid = None
                    moveset = False
                    await utils.safe_delete(message)
                    auto_report = True if int(egg_level) in self.bot.guild_dict[message.guild.id]['configure_dict']['scanners']['egglvls'] else False
                for channelid in self.bot.guild_dict[message.guild.id]['raidchannel_dict']:
                    channel_gps = self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid].get('coordinates', None)
                    channel_address = self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid].get('address', None)
                    if not channel_gps:
                        continue
                    if channel_gps == huntrgps or channel_address == raid_details:
                        channel = self.bot.get_channel(channelid)
                        if self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid]['type'] == 'egg':
                            await raid_cog._eggtoraid(entered_raid.lower().strip(), channel, author=message.author, huntr=moveset)
                        raidmsg = await channel.fetch_message(self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid]['raid_message'])
                        if moveset and raidmsg.embeds[0].fields[2].name != moveset:
                            await channel.send(_("This {entered_raid}'s moves are: **{moves}**").format(entered_raid=entered_raid.title(), moves=moveset))
                        return
                if auto_report and reporttype == "raid":
                    report_details = {
                        "pokemon":entered_raid,
                        "gym":raid_details,
                        "raidexp":raidexp,
                        "gps":huntrgps,
                        "moves":moveset
                    }
                    await self.huntr_raid(ctx, report_details)
                elif auto_report and reporttype == "egg":
                    report_details = {
                        "level":egg_level,
                        "gym":raid_details,
                        "raidexp":raidexp,
                        "gps":huntrgps
                    }
                    await self.huntr_raidegg(ctx, report_details)
                elif reporttype == "raid":
                    gym_matching_cog = self.bot.cogs.get('GymMatching')
                    if gym_matching_cog:
                        test_gym = await gym_matching_cog.find_nearest_gym((huntrgps.split(",")[0], huntrgps.split(",")[1]), message.guild.id)
                        if test_gym:
                            raid_details = test_gym
                    raid_embed = await self.make_raid_embed(ctx, entered_raid, raid_details, raidexp, huntrgps, moveset)
                    if not raid_embed:
                        return
                    raid = discord.utils.get(message.guild.roles, name=entered_raid.lower())
                    if raid == None:
                        roletest = ""
                    else:
                        roletest = _("{pokemon} - ").format(pokemon=raid.mention)
                    pokehuntr_dict = self.bot.guild_dict[message.guild.id].setdefault('pokehuntr_dict', {})
                    ctx.raidreport = await message.channel.send(content=_('{roletest}Meowth! {pokemon} raid reported by {member}! Details: {location_details}. React if you want to make a channel for this raid!').format(roletest=roletest, pokemon=entered_raid.title(), member=message.author.mention, location_details=raid_details), embed=raid_embed)
                    await asyncio.sleep(0.25)
                    await utils.safe_reaction(ctx.raidreport, self.bot.custom_emoji.get('huntr_report', '\u2705'))
                    for reaction in react_list:
                        await utils.safe_reaction(ctx.raidreport, reaction)
                    dm_dict = await raid_cog.send_dm_messages(ctx, raid_details, f"Meowth! {entered_raid.title()} raid reported by {message.author.display_name} in {message.channel.mention}! Details: {raid_details}. React in {message.channel.mention} to report this raid!", copy.deepcopy(raid_embed), dm_dict)
                    self.bot.guild_dict[message.guild.id]['pokehuntr_dict'][ctx.raidreport.id] = {
                        "exp":time.time() + (raidexp * 60),
                        "raidexp":raidexp,
                        'expedit': {"content":ctx.raidreport.content.split(" React")[0], "embedcontent":_('**This {pokemon} raid has expired!**').format(pokemon=entered_raid)},
                        "reporttype":"raid",
                        'report_channel':message.channel.id,
                        "level":0,
                        "pokemon":entered_raid,
                        "reporttime":now,
                        "gym":raid_details,
                        "gps":huntrgps,
                        "moves":moveset,
                        "embed":raid_embed,
                        "dm_dict": dm_dict
                    }
                elif reporttype == "egg":
                    gym_matching_cog = ctx.bot.cogs.get('GymMatching')
                    if gym_matching_cog:
                        test_gym = await gym_matching_cog.find_nearest_gym((huntrgps.split(",")[0], huntrgps.split(",")[1]), message.guild.id)
                        if test_gym:
                            raid_details = test_gym
                    raid_embed = await self.make_egg_embed(ctx, egg_level, raid_details, raidexp, huntrgps, reporter="huntr")
                    if not raid_embed:
                        return
                    pokehuntr_dict = self.bot.guild_dict[message.guild.id].setdefault('pokehuntr_dict', {})
                    ctx.raidreport = await message.channel.send(content=_('Meowth! Level {level} raid egg reported by {member}! Details: {location_details}. React if you want to make a channel for this raid!').format(level=egg_level, member=message.author.mention, location_details=raid_details), embed=raid_embed)
                    await asyncio.sleep(0.25)
                    await utils.safe_reaction(ctx.raidreport, self.bot.custom_emoji.get('huntr_report', '\u2705'))
                    for reaction in react_list:
                        await utils.safe_reaction(ctx.raidreport, reaction)
                    dm_dict = await raid_cog.send_dm_messages(ctx, raid_details, f"Meowth! Level {egg_level} raid egg reported by {message.author.display_name} in {message.channel.mention}! Details: {raid_details}. React in {message.channel.mention} to report this raid!", copy.deepcopy(raid_embed), dm_dict)
                    self.bot.guild_dict[message.guild.id]['pokehuntr_dict'][ctx.raidreport.id] = {
                        "exp":time.time() + (int(raidexp) * 60),
                        "raidexp":raidexp,
                        'expedit': {"content":ctx.raidreport.content.split(" React")[0], "embedcontent": _('**This level {level} raid egg has hatched!**').format(level=egg_level)},
                        "reporttype":"egg",
                        "report_channel":message.channel.id,
                        "level":egg_level,
                        "pokemon":None,
                        "reporttime":now,
                        "gym":raid_details,
                        "gps":huntrgps,
                        "moves":None,
                        "embed":raid_embed,
                        "dm_dict":dm_dict
                    }
            if (message.author.id == 295116861920772098 or message.author.id == message.guild.me.id) and message.embeds and auto_wild:
                wild_cog = self.bot.cogs.get('Wild')
                if not wild_cog:
                    logger.error("Wild Cog not loaded")
                    return
                reporttype = "wild"
                hpokeid = message.embeds[0].title.split(' ')[2].lower()
                hdesc = message.embeds[0].description.splitlines()
                hexpire = None
                hweather = None
                hiv = None
                huntrgps = "https://pokehuntr.com/#{huntrgps}".format(huntrgps=huntrgps)
                for line in hdesc:
                    if "remaining:" in line.lower():
                        hexpire = line.split(': ')[1][:(- 1)]
                    if "weather:" in line.lower():
                        hweather = line.split(': ')[1][1:(- 1)]
                    if "iv:" in line.lower():
                        hiv = line.split(': ')[1][2:(-2)].replace("%", "")
                hextra = "Weather: {hweather}".format(hweather=hweather)
                if hiv:
                    hextra += " / IV: {hiv}".format(hiv=hiv)
                await utils.safe_delete(message)
                huntr_details = {"pokemon":hpokeid, "coordinates":huntrgps, "expire":hexpire, "weather":hweather, "iv_percent":hiv}
                await self.huntr_wild(ctx, huntr_details, reporter="huntr")
                return
        else:
            raid_cog = self.bot.cogs.get('Raid')
            if not raid_cog:
                logger.error("Raid Cog not loaded")
                return
            await utils.safe_delete(message)
            pokehuntr_dict = copy.deepcopy(self.bot.guild_dict[message.guild.id].get('pokehuntr_dict', {}))
            reporttime = pokehuntr_dict[message.id]['reporttime']
            reporttype = pokehuntr_dict[message.id]['reporttype']
            coordinates = pokehuntr_dict[message.id]['gps']
            raid_details = pokehuntr_dict[message.id]['gym'].strip()
            dm_dict = copy.deepcopy(pokehuntr_dict[message.id]['dm_dict'])
            reacttime = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])
            timediff = relativedelta(reacttime, reporttime)
            raidexp = int(reporttime.minute) - int(timediff.minutes)
            if reporttype == "egg":
                egg_level = pokehuntr_dict[message.id]['level']
                report_details = {
                    "level":egg_level,
                    "gym":raid_details,
                    "raidexp":raidexp,
                    "gps":coordinates
                }
                raid_channel = await self.huntr_raidegg(ctx, report_details, report_user=reactuser, dm_dict=dm_dict)
                return raid_channel
            elif reporttype == "raid":
                entered_raid = pokehuntr_dict[message.id]['pokemon']
                moveset = pokehuntr_dict[message.id]['moves']
                report_details = {
                    "pokemon":entered_raid,
                    "gym":raid_details,
                    "raidexp":raidexp,
                    "gps":coordinates,
                    "moves":moveset
                }
                raid_channel = await self.huntr_raid(ctx, report_details, report_user=reactuser, dm_dict=dm_dict)
                return raid_channel

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
        huntr_emoji = self.bot.custom_emoji.get('huntr_report', '\u2705')
        maybe_reaction = self.bot.custom_emoji.get('raid_maybe', '\u2753')
        omw_reaction = self.bot.custom_emoji.get('raid_omw', '\ud83c\udfce')
        here_reaction = self.bot.custom_emoji.get('raid_here', '\U0001F4CD')
        react_list = [huntr_emoji, maybe_reaction, omw_reaction, here_reaction]
        if not reactuser:
            reporttype = None
            report = None
            embed = message.embeds[0] if message.embeds else None
            now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])
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
                            await raid_cog._eggtoraid(report_details.get('pokemon', None), channel, message.author, huntr=report_details.get('moves', None))
                        elif channel and report_details.get('moves', None):
                            await channel.send(_("This {entered_raid}'s moves are: **{moves}**").format(entered_raid=report_details.get('pokemon', None).title(), moves=report_details.get('moves', None)))
                            try:
                                raid_msg = await channel.fetch_message(self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid]['raid_message'])
                            except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                                return
                            raid_embed = raid_msg.embeds[0]
                            for field in raid_embed.fields:
                                if "moveset" in field.name.lower():
                                    return
                            raid_embed.add_field(name="**Moveset**:", value=report_details.get('moves', None), inline=True)
                            await raid_msg.edit(embed=raid_embed)
                        raidexp = report_details.get('raidexp')
                        if raidexp and channel:
                            await raid_cog._timerset(channel, raidexp)
                        await self.auto_counters(channel, report_details.get('moves', None))
                        return
                if report_details.get('type', None) == "raid":
                    if not self.bot.guild_dict[message.guild.id]['configure_dict']['scanners'].get('reports', {}).get('raid'):
                        return
                    reporttype = "raid"
                    pokemon = report_details.setdefault('pokemon', None)
                    if not utils.get_level(self.bot, pokemon):
                        logger.error(f"{pokemon} not in raid_json")
                        return
                    coordinates = report_details.setdefault('gps', None)
                    raid_details = report_details.setdefault('gym', None)
                    if not all([pokemon, coordinates, raid_details]):
                        return
                    egg_level = "0"
                    timeout = int(report_details.get('raidexp', 45))*60
                    expiremsg = _('**This {pokemon} raid has expired!**').format(pokemon=pokemon.title())
                    if int(utils.get_level(self.bot, pokemon)) in self.bot.guild_dict[message.guild.id]['configure_dict']['scanners'].get('raidlvls', []):
                        raid_channel = await self.huntr_raid(ctx, report_details)
                        if embed and raid_channel:
                            await raid_channel.send(embed=embed)
                        return
                    else:
                        pokemon = await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, pokemon)
                        if not pokemon:
                            return
                        raid = discord.utils.get(message.guild.roles, name=pokemon.name.lower())
                        if raid == None:
                            roletest = ""
                        else:
                            roletest = _("{pokemon} - ").format(pokemon=raid.mention)
                        raidmsg = f"{roletest}Meowth! {pokemon.name.title()} raid reported by {message.author.mention}! Details: {raid_details}. React below if you want to make a channel for this raid!"
                        ctx.raidreport = await message.channel.send(raidmsg, embed=embed)
                        dm_dict = await raid_cog.send_dm_messages(ctx, raid_details, f"Meowth! {pokemon.name.title()} raid reported by {message.author.display_name} in {message.channel.mention}! Details: {raid_details}. React in {message.channel.mention} to report this raid!", copy.deepcopy(embed), dm_dict)
                elif report_details.get('type', None) == "egg":
                    if not self.bot.guild_dict[message.guild.id]['configure_dict']['scanners'].get('reports', {}).get('egg'):
                        return
                    reporttype = "egg"
                    egg_level = report_details.setdefault('level', None)
                    coordinates = report_details.setdefault('gps', None)
                    raid_details = report_details.setdefault('gym', None)
                    if not all([egg_level, coordinates, raid_details]):
                        return
                    moves = None
                    pokemon = None
                    egg_level = str(egg_level)
                    timeout = int(report_details.get('raidexp', 45))*60
                    expiremsg = ('This level {level} raid egg has hatched!').format(level=egg_level)
                    if int(egg_level) in self.bot.guild_dict[message.guild.id]['configure_dict']['scanners'].get('egglvls', False):
                        raid_channel = await self.huntr_raidegg(ctx, report_details)
                        if embed and raid_channel:
                            await raid_channel.send(embed=embed)
                        return
                    else:
                        raidmsg = f"Meowth! Level {egg_level} raid egg reported by {message.author.mention}! Details: {raid_details}. React below if you want to make a channel for this egg!"
                        ctx.raidreport = await message.channel.send(raidmsg, embed=embed)
                        dm_dict = await raid_cog.send_dm_messages(ctx, raid_details, f"Meowth! Level {egg_level} raid egg reported by {message.author.display_name} in {message.channel.mention}! Details: {raid_details}. React in {message.channel.mention} to report this raid!", copy.deepcopy(embed), dm_dict)
                self.bot.guild_dict[message.guild.id]['pokealarm_dict'][ctx.raidreport.id] = {
                    "exp":time.time() + timeout,
                    'expedit': {"content":raidmsg.split("React")[0], "embedcontent":expiremsg},
                    "reporttype":reporttype,
                    "report_channel":message.channel.id,
                    "level":egg_level,
                    "pokemon":str(pokemon) if pokemon else None,
                    "gps":coordinates,
                    "gym":raid_details,
                    "raidexp":report_details.setdefault('raidexp', 45),
                    "reporttime":now,
                    "moves":report_details.setdefault('moves', None),
                    "embed":embed,
                    "dm_dict":dm_dict
                }
                await asyncio.sleep(0.25)
                for reaction in react_list:
                    await utils.safe_reaction(ctx.raidreport, reaction)
                return
            elif report_details.get('type', None) == "wild":
                if not self.bot.guild_dict[message.guild.id]['configure_dict']['scanners'].get('reports', {}).get('wild'):
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
                if not self.bot.guild_dict[message.guild.id]['configure_dict']['scanners'].get('reports', {}).get('research'):
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
                if not self.bot.guild_dict[message.guild.id]['configure_dict']['scanners'].get('reports', {}).get('lure'):
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
                if not self.bot.guild_dict[message.guild.id]['configure_dict']['scanners'].get('reports', {}).get('invasion'):
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
            reacttime = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])
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

    """Helpers"""

    async def auto_counters(self, channel, moves):
        moveset = 0
        newembed = False
        raid_cog = self.bot.cogs.get('Raid')
        if not raid_cog:
            logger.error("Raid Cog not loaded")
            return
        try:
            ctrs_message = await channel.fetch_message(self.bot.guild_dict[channel.guild.id]['raidchannel_dict'][channel.id]['ctrsmessage'])
        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException, KeyError):
            ctrs_message = None
        except AttributeError:
            return
        ctrs_dict = self.bot.guild_dict[channel.guild.id]['raidchannel_dict'][channel.id].get('ctrs_dict', {})
        entered_raid = self.bot.guild_dict[channel.guild.id]['raidchannel_dict'][channel.id].get('pokemon', "")
        weather =  self.bot.guild_dict[channel.guild.id]['raidchannel_dict'][channel.id].get('weather', None)
        if not ctrs_dict:
            ctrs_dict = await raid_cog._get_generic_counters(channel.guild, entered_raid, weather)
            self.bot.guild_dict[channel.guild.id]['raidchannel_dict'][channel.id]['ctrs_dict'] = ctrs_dict
        if not moves or not ctrs_dict:
            return
        moves = re.split('\\||/|,', moves)
        moves = [x.strip() for x in moves]
        for i in ctrs_dict:
            if ctrs_dict[i]['moveset'] == (' | ').join(moves):
                newembed = ctrs_dict[i]['embed']
                moveset = i
                break
        if ctrs_message and newembed:
            await ctrs_message.edit(embed=newembed)
        self.bot.guild_dict[channel.guild.id]['raidchannel_dict'][channel.id]['moveset'] = moveset

    async def auto_weather(self, ctx, coord):
        wild_dict = self.bot.guild_dict[ctx.guild.id]['wildreport_dict']
        wild_weather_dict = {}
        for wild_report in list(wild_dict.keys()):
            report_time = datetime.datetime.utcfromtimestamp(wild_dict.get(wild_report, {}).get('report_time', time.time()))
            coordinates = wild_dict.get(wild_report, {}).get('coordinates', None)
            weather = wild_dict.get(wild_report, {}).get('weather', None)
            if weather and coordinates and ctx.message.created_at.hour == report_time.hour:
                wild_weather_dict[coordinates] = weather
        if not wild_weather_dict:
            return None
        weather_search = {k: (float(k.split(",")[0]), float(k.split(",")[1])) for k,v in wild_weather_dict.items()}
        dist = lambda s, key: (float(s[0]) - float(weather_search[key][0])) ** 2 + \
                              (float(s[1]) - float(weather_search[key][1])) ** 2
        nearest_wild = min(weather_search, key=functools.partial(dist, coord))
        return wild_weather_dict[nearest_wild]

    async def make_egg_embed(self, ctx, egg_level, raid_details, raidexp, raid_coordinates, reporter=None):
        message = ctx.message
        timestamp = (message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])).strftime(_('%I:%M %p (%H:%M)'))
        raid_gmaps_link = f"https://www.google.com/maps/search/?api=1&query={raid_coordinates}"
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        gym_info = ""
        if gym_matching_cog:
            gym_info, raid_details, gym_url = await gym_matching_cog.get_poi_info(ctx, raid_details, "raid")
            if gym_url:
                raid_gmaps_link = gym_url
        if not raid_details:
            return None
        egg_level = str(egg_level)
        egg_info = ctx.bot.raid_info['raid_eggs'][egg_level]
        egg_img = egg_info['egg_img']
        boss_list = []
        for p in egg_info['pokemon']:
            shiny_str = ""
            pokemon = await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, p)
            if pokemon.id in self.bot.shiny_dict:
                if pokemon.alolan and "alolan" in self.bot.shiny_dict.get(pokemon.id, {}) and "raid" in self.bot.shiny_dict.get(pokemon.id, {}).get("alolan", []):
                    shiny_str = self.bot.custom_emoji.get('shiny_chance', '\u2728') + " "
                elif str(pokemon.form).lower() in self.bot.shiny_dict.get(pokemon.id, {}) and "raid" in self.bot.shiny_dict.get(pokemon.id, {}).get(str(pokemon.form).lower(), []):
                    shiny_str = self.bot.custom_emoji.get('shiny_chance', '\u2728') + " "
            boss_list.append(shiny_str + pokemon.name.title() + ' (' + str(pokemon.id) + ') ' + pokemon.emoji)
        raid_img_url = 'https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/eggs/{}?cache=1'.format(str(egg_img))
        raid_embed = discord.Embed(title=_('Meowth! Click here for directions to the coming level {level} raid!').format(level=egg_level), description=gym_info, url=raid_gmaps_link, colour=message.guild.me.colour)
        if len(egg_info['pokemon']) > 1:
            raid_embed.add_field(name=_('**Possible Bosses:**'), value=_('{bosslist1}').format(bosslist1='\n'.join(boss_list[::2])), inline=True)
            raid_embed.add_field(name=_('**Possible Bosses:**'), value=_('{bosslist2}').format(bosslist2='\n'.join(boss_list[1::2])), inline=True)
        else:
            raid_embed.add_field(name=_('**Possible Bosses:**'), value=_('{bosslist}').format(bosslist=''.join(boss_list)), inline=True)
            raid_embed.add_field(name=_('**Weaknesses:**'), value='\u200b', inline=True)
        raid_embed.add_field(name=_('**Next Group:**'), value=_('Set with **!starttime**'), inline=True)
        raid_embed.add_field(name=_('**Hatches:**'), value=_('Set with **!timerset**'), inline=True)
        if reporter == "huntr":
            raid_embed.add_field(name="\u200b", value=_("Perform a scan to help find more by clicking [here](https://gymhuntr.com/#{huntrurl}).").format(huntrurl=raid_coordinates), inline=False)
        raid_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=message.author.display_name, timestamp=timestamp), icon_url=message.author.avatar_url_as(format=None, static_format='jpg', size=32))
        raid_embed.set_thumbnail(url=raid_img_url)
        raid_embed.set_author(name=f"Level {egg_level} Raid Report", icon_url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/eggs/{egg_level}.png?cache=1")
        return raid_embed

    async def make_raid_embed(self, ctx, entered_raid, raid_details, raidexp, raid_coordinates, moveset=None, reporter=None):
        message = ctx.message
        timestamp = (message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])).strftime(_('%I:%M %p (%H:%M)'))
        raid_gmaps_link = f"https://www.google.com/maps/search/?api=1&query={raid_coordinates}"
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        pokemon = await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, entered_raid)
        if pokemon:
            entered_raid = pokemon.name.lower()
            pokemon.shiny = False
            pokemon.gender = False
        level = utils.get_level(ctx.bot, pokemon.id)
        gym_info = ""
        if gym_matching_cog:
            gym_info, raid_details, gym_url = await gym_matching_cog.get_poi_info(ctx, raid_details, "raid")
            if gym_url:
                raid_gmaps_link = gym_url
        if not raid_details:
            await utils.safe_delete(ctx.message)
            return None
        raid = discord.utils.get(message.guild.roles, name=entered_raid)
        if raid == None:
            roletest = ""
        else:
            roletest = _("{pokemon} - ").format(pokemon=raid.mention)
        shiny_str = ""
        if pokemon.id in self.bot.shiny_dict:
            if pokemon.alolan and "alolan" in self.bot.shiny_dict.get(pokemon.id, {}) and "raid" in self.bot.shiny_dict.get(pokemon.id, {}).get("alolan", []):
                shiny_str = self.bot.custom_emoji.get('shiny_chance', '\u2728') + " "
            elif str(pokemon.form).lower() in self.bot.shiny_dict.get(pokemon.id, {}) and "raid" in self.bot.shiny_dict.get(pokemon.id, {}).get(str(pokemon.form).lower(), []):
                shiny_str = self.bot.custom_emoji.get('shiny_chance', '\u2728') + " "
        raid_number = pokemon.id
        raid_embed = discord.Embed(title=_('Meowth! Click here for directions to the level {level} raid!').format(level=level), description=gym_info, url=raid_gmaps_link, colour=message.guild.me.colour)
        raid_embed.add_field(name=_('**Details:**'), value=f"{shiny_str}{pokemon.name.title()} ({pokemon.id}) {pokemon.emoji}", inline=True)
        raid_embed.add_field(name=_('**Weaknesses:**'), value=_('{weakness_list}\u200b').format(weakness_list=utils.weakness_to_str(ctx.bot, message.guild, utils.get_weaknesses(ctx.bot, pokemon.name.lower(), pokemon.form, pokemon.alolan))), inline=True)
        raid_embed.add_field(name=_('**Next Group:**'), value=_('Set with **!starttime**'), inline=True)
        raid_embed.add_field(name=_('**Expires:**'), value=_('Set with **!timerset**'), inline=True)
        if moveset:
            raid_embed.add_field(name=_("**Moveset:**"), value=moveset)
        raid_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=message.author.display_name, timestamp=timestamp), icon_url=message.author.avatar_url_as(format=None, static_format='jpg', size=32))
        raid_embed.set_thumbnail(url=pokemon.img_url)
        raid_embed.set_author(name=f"{pokemon.name.title()} Raid Report", icon_url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/raid_tut_raid.png?cache=1")
        return raid_embed

    """Reporting"""

    async def huntr_wild(self, ctx, report_details, reporter=None, report_user=None, dm_dict=None):
        if not dm_dict:
            dm_dict = {}
        if report_user:
            ctx.message.author = report_user
        message = ctx.message
        pokemon = await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, report_details['pokemon'])
        if pokemon:
            entered_wild = pokemon.name.lower()
            pokemon.shiny = False
        else:
            return
        if pokemon.id in ctx.bot.guild_dict[message.channel.guild.id]['configure_dict']['scanners'].setdefault('wildfilter', []):
            if not report_details.get("iv_percent", '') and not report_details.get("level", ''):
                return
        gender = report_details.setdefault("gender", pokemon.gender)
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
        elif "windy" in weather:
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
        omw_emoji = ctx.bot.custom_emoji.get('wild_omw', '\U0001F3CE')
        despawn_emoji = ctx.bot.custom_emoji.get('wild_despawn', '\U0001F4A8')
        info_emoji = ctx.bot.custom_emoji.get('wild_info', '\u2139')
        catch_emoji = ctx.bot.custom_emoji.get('wild_catch', '\u26BE')
        list_emoji = ctx.bot.custom_emoji.get('list_emoji', '\U0001f5d2')
        reaction_list = [omw_emoji, catch_emoji, despawn_emoji, info_emoji, list_emoji]
        despawn = (int(expire.split(' ')[0]) * 60) + int(expire.split(' ')[2])
        if despawn < 2700:
            reaction_list.remove(despawn_emoji)
        ctx.wildreportmsg = await message.channel.send(f"Meowth! Wild {str(pokemon).title()} reported by {message.author.mention}!{stop_str}Coordinates: {wild_coordinates}{iv_str}\nUse {omw_emoji} if on your way, {catch_emoji} if you caught it{', ' + despawn_emoji + ' if it despawned' if despawn >= 2700 else ''}, {info_emoji} to edit details, or {list_emoji} to list all wilds!", embed=wild_embed)
        dm_dict = await wild_cog.send_dm_messages(ctx, str(pokemon), str(nearest_stop), iv_percent, level, ctx.wildreportmsg.content.replace(ctx.author.mention, f"{ctx.author.display_name} in {ctx.channel.mention}"), wild_embed.copy(), dm_dict)
        for reaction in reaction_list:
            await asyncio.sleep(0.25)
            await utils.safe_reaction(ctx.wildreportmsg, reaction)
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
            ctx.message.author = report_user
        message = ctx.message
        help_reaction = self.bot.custom_emoji.get('raid_info', '\u2139')
        maybe_reaction = self.bot.custom_emoji.get('raid_maybe', '\u2753')
        omw_reaction = self.bot.custom_emoji.get('raid_omw', '\ud83c\udfce')
        here_reaction = self.bot.custom_emoji.get('raid_here', '\U0001F4CD')
        cancel_reaction = self.bot.custom_emoji.get('raid_cancel', '\u274C')
        list_emoji = ctx.bot.custom_emoji.get('list_emoji', '\U0001f5d2')
        react_list = [maybe_reaction, omw_reaction, here_reaction, cancel_reaction]
        timestamp = (message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])).strftime(_('%I:%M %p (%H:%M)'))
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])
        entered_raid = report_details['pokemon']
        raid_coordinates = report_details['gps']
        raid_details = report_details.get('gym', raid_coordinates)
        moves = report_details.get('moves', None)
        raidexp = report_details.get('raidexp', 45)
        pokemon = await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, entered_raid)
        if pokemon:
            pokemon.shiny = False
            pokemon.gender = False
        else:
            return
        if not pokemon.id in ctx.bot.raid_list:
            await message.channel.send(_('Meowth! The Pokemon {pokemon} does not appear in raids!').format(pokemon=entered_raid.capitalize()), delete_after=10)
            return
        elif utils.get_level(ctx.bot, entered_raid) == "EX":
            await message.channel.send(_("Meowth! The Pokemon {pokemon} only appears in EX Raids! Use **!exraid** to report one!").format(pokemon=entered_raid.capitalize()), delete_after=10)
            return
        level = utils.get_level(ctx.bot, pokemon.id)
        matched_boss = False
        for boss in self.bot.raid_info['raid_eggs'][str(level)]['pokemon']:
            boss = await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, boss)
            if str(boss) == str(pokemon):
                pokemon = boss
                entered_raid = boss.name.lower()
                matched_boss = True
                break
        if not matched_boss:
            for boss in self.bot.raid_info['raid_eggs'][str(level)]['pokemon']:
                boss = await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, boss)
                if boss and boss.id == pokemon.id:
                    pokemon = boss
                    entered_raid = boss.name.lower()
                    break
        weather = ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'].get(message.channel.id, {}).get('weather', None)
        if not weather:
            weather = await self.auto_weather(ctx, raid_coordinates)
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        if gym_matching_cog:
            test_gym = await gym_matching_cog.find_nearest_gym((raid_coordinates.split(",")[0], raid_coordinates.split(",")[1]), message.guild.id)
            if test_gym:
                raid_details = test_gym
        raid_embed = await self.make_raid_embed(ctx, str(pokemon), raid_details, raidexp, raid_coordinates, moves)
        if not raid_embed:
            return
        raid_channel = await raid_cog.create_raid_channel(ctx, entered_raid, raid_details, "raid")
        if not raid_channel:
            return
        await asyncio.sleep(1)
        ctx.raidreport = await message.channel.send(content=f"Meowth! {str(pokemon).title()} raid reported by {message.author.mention}! Details: {raid_details}. Coordinate in {raid_channel.mention}\nUse {maybe_reaction} if you are interested, {omw_reaction} if you are on your way, {here_reaction} if you are at the raid, {cancel_reaction} to cancel, or {list_emoji} to list all raids!", embed=raid_embed)
        raid = discord.utils.get(message.guild.roles, name=pokemon.name.lower())
        if raid == None:
            roletest = ""
        else:
            roletest = _("{pokemon} - ").format(pokemon=raid.mention)
        raidmsg = f"{roletest}Meowth! {str(pokemon).title()} raid reported by {message.author.mention} in {message.channel.mention}! Details: {raid_details}. Coordinate here!\n\nClick the {help_reaction} to get help on commands, {maybe_reaction} if you are interested, {omw_reaction} if you are on your way, {here_reaction} if you are at the raid, or {cancel_reaction} to cancel.\n\nThis channel will be deleted five minutes after the timer expires."
        raid_message = await raid_channel.send(content=raidmsg, embed=raid_embed)
        await utils.safe_reaction(raid_message, help_reaction)
        for reaction in react_list:
            await asyncio.sleep(0.25)
            await utils.safe_reaction(raid_message, reaction)
            await asyncio.sleep(0.25)
            await utils.safe_reaction(ctx.raidreport, reaction)
        await utils.safe_reaction(ctx.raidreport, list_emoji)
        await raid_message.pin()
        level = utils.get_level(self.bot, entered_raid)
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
            'report_message':message.id,
            'address': raid_details,
            'location':raid_details,
            'type': 'raid',
            'pokemon': entered_raid,
            'pkmn_obj': str(pokemon),
            'egg_level': '0',
            'moveset': 0,
            'weather': weather,
            'coordinates':raid_coordinates
        }
        await raid_cog._timerset(raid_channel, raidexp)
        await raid_channel.send(f"This raid was reported by a bot. If it is a duplicate of a raid already reported by a human, I can delete it with three **!duplicate** messages.\nThe weather may be inaccurate for this raid, use **{ctx.prefix}weather** to set the correct weather.")
        ctrs_dict = await raid_cog._get_generic_counters(message.guild, entered_raid, weather)
        if str(level) in ctx.bot.guild_dict[message.guild.id]['configure_dict']['counters']['auto_levels']:
            try:
                ctrsmsg = "Here are the best counters for the raid boss in currently known weather conditions! Update weather with **!weather**. If you know the moveset of the boss, you can react to this message with the matching emoji and I will update the counters."
                ctrsmessage = await raid_channel.send(content=ctrsmsg, embed=ctrs_dict[0]['embed'])
                ctrsmessage_id = ctrsmessage.id
                await ctrsmessage.pin()
                for moveset in ctrs_dict:
                    await utils.safe_reaction(ctrsmessage, ctrs_dict[moveset]['emoji'])
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
        self.bot.loop.create_task(raid_cog.edit_dm_messages(ctx, ctx.raidreport.content, copy.deepcopy(raid_embed), dm_dict))
        dm_dict = await raid_cog.send_dm_messages(ctx, raid_details, ctx.raidreport.content.replace(ctx.author.mention, f"{ctx.author.display_name} in {ctx.channel.mention}"), copy.deepcopy(raid_embed), dm_dict)
        ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid_channel.id]['dm_dict'] = dm_dict
        if report_user:
            raid_reports = self.bot.guild_dict[message.guild.id].setdefault('trainers', {}).setdefault(report_user.id, {}).setdefault('reports', {}).setdefault('raid', 0) + 1
            self.bot.guild_dict[message.guild.id]['trainers'][report_user.id]['reports']['raid'] = raid_reports
        await self.auto_counters(raid_channel, moves)
        return raid_channel

    async def huntr_raidegg(self, ctx, report_details, reporter=None, report_user=None, dm_dict=None):
        if not dm_dict:
            dm_dict = {}
        raid_cog = self.bot.cogs.get('Raid')
        if report_user:
            ctx.message.author = report_user
        message = ctx.message
        help_reaction = self.bot.custom_emoji.get('raid_info', '\u2139')
        maybe_reaction = self.bot.custom_emoji.get('raid_maybe', '\u2753')
        omw_reaction = self.bot.custom_emoji.get('raid_omw', '\ud83c\udfce')
        here_reaction = self.bot.custom_emoji.get('raid_here', '\U0001F4CD')
        cancel_reaction = self.bot.custom_emoji.get('raid_cancel', '\u274C')
        list_emoji = ctx.bot.custom_emoji.get('list_emoji', '\U0001f5d2')
        react_list = [maybe_reaction, omw_reaction, here_reaction, cancel_reaction]
        timestamp = (message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])).strftime(_('%I:%M %p (%H:%M)'))
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])
        egg_level = str(report_details.get('level'))
        raid_details = report_details.get('gym')
        raidexp = report_details.get('raidexp', 60)
        raid_coordinates = report_details['gps']
        weather = ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'].get(message.channel.id, {}).get('weather', None)
        if not weather:
            weather = await self.auto_weather(ctx, raid_coordinates)
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        if gym_matching_cog:
            test_gym = await gym_matching_cog.find_nearest_gym((raid_coordinates.split(",")[0], raid_coordinates.split(",")[1]), message.guild.id)
            if test_gym:
                raid_details = test_gym
        raid_embed = await self.make_egg_embed(ctx, egg_level, raid_details, raidexp, raid_coordinates, reporter)
        if not raid_embed:
            return
        raid_channel = await raid_cog.create_raid_channel(ctx, egg_level, raid_details, "egg")
        if not raid_channel:
            return
        await asyncio.sleep(1)
        ctx.raidreport = await message.channel.send(content=f"Meowth! Level {egg_level} raid egg reported by {message.author.mention}! Details: {raid_details}. Coordinate in {raid_channel.mention}\nUse {maybe_reaction} if you are interested, {omw_reaction} if you are on your way, {here_reaction} if you are at the raid, {cancel_reaction} to cancel, or {list_emoji} to list all raids!", embed=raid_embed)
        raidmsg = f"Meowth! Level {egg_level} raid egg reported by {message.author.mention} in {message.channel.mention}! Details: {raid_details}. Coordinate here!\n\nClick the {help_reaction} to get help on commands, {maybe_reaction} if you are interested, {omw_reaction} if you are on your way, {here_reaction} if you are at the raid, or {cancel_reaction} to cancel.\n\nThis channel will be deleted five minutes after the timer expires."
        raid_message = await raid_channel.send(content=raidmsg, embed=raid_embed)
        await utils.safe_reaction(raid_message, help_reaction)
        for reaction in react_list:
            await asyncio.sleep(0.25)
            await utils.safe_reaction(raid_message, reaction)
            await asyncio.sleep(0.25)
            await utils.safe_reaction(ctx.raidreport, reaction)
        await utils.safe_reaction(ctx.raidreport, list_emoji)
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
            'report_message':message.id,
            'address': raid_details,
            'type': 'egg',
            'pokemon': '',
            'egg_level':egg_level,
            'weather': weather,
            'moveset': 0,
            'coordinates':raid_coordinates
        }
        if raidexp is not False:
            await raid_cog._timerset(raid_channel, raidexp)
        else:
            await raid_channel.send(content=_('Meowth! Hey {member}, if you can, set the time left until the egg hatches using **!timerset <minutes>** so others can check it with **!timer**.').format(member=message.author.mention))
        await raid_channel.send(f"This egg was reported by a bot. If it is a duplicate of a raid already reported by a human, I can delete it with three **!duplicate** messages.\nThe weather may be inaccurate for this raid, use **{ctx.prefix}weather** to set the correct weather.")
        if len(ctx.bot.raid_info['raid_eggs'][egg_level]['pokemon']) == 1:
            pokemon = await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, ctx.bot.raid_info['raid_eggs'][egg_level]['pokemon'][0])
            pokemon = pokemon.name.lower()
            await raid_cog._eggassume(ctx, 'assume ' + pokemon, raid_channel)
        elif egg_level == "5" and ctx.bot.guild_dict[raid_channel.guild.id]['configure_dict']['settings'].get('regional', None) in ctx.bot.raid_list:
            pokemon = await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, ctx.bot.guild_dict[raid_channel.guild.id]['configure_dict']['settings']['regional'])
            pokemon = pokemon.name.lower()
            await raid_cog._eggassume(ctx, 'assume ' + pokemon, raid_channel)
        self.event_loop.create_task(raid_cog.expiry_check(raid_channel))
        index = 0
        for field in raid_embed.fields:
            if "reaction" in field.name.lower() or "status" in field.name.lower() or "team" in field.name.lower():
                raid_embed.remove_field(index)
            else:
                index += 1
        self.bot.loop.create_task(raid_cog.edit_dm_messages(ctx, ctx.raidreport.content, copy.deepcopy(raid_embed), dm_dict))
        dm_dict = await raid_cog.send_dm_messages(ctx, raid_details, ctx.raidreport.content.replace(ctx.author.mention, f"{ctx.author.display_name} in {ctx.channel.mention}"), copy.deepcopy(raid_embed), dm_dict)
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
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset']))
        to_midnight = 24*60*60 - ((timestamp-timestamp.replace(hour=0, minute=0, second=0, microsecond=0)).seconds)
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        stop_info = ""
        if gym_matching_cog:
            nearest_stop = await gym_matching_cog.find_nearest_stop((gps.split(",")[0],gps.split(",")[1]), guild.id)
            if nearest_stop:
                location = nearest_stop
            stop_info, location, stop_url = await gym_matching_cog.get_poi_info(ctx, location, "research")
            if stop_url:
                loc_url = stop_url
        if not location:
            return
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
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        stop_info = ""
        if gym_matching_cog:
            nearest_stop = await gym_matching_cog.find_nearest_stop((gps.split(",")[0],gps.split(",")[1]), guild.id)
            if nearest_stop:
                location = nearest_stop
            stop_info, location, stop_url = await gym_matching_cog.get_poi_info(ctx, location, "invasion")
        if not location:
            return
        await invasion_cog.send_invasion(ctx, location, reward, gender, timer)

    @commands.command(hidden=True)
    @commands.has_permissions(manage_guild=True)
    async def huntrraid(self, ctx):
        """Simulates a huntr raid"""
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        await utils.safe_delete(message)
        tier5 = str(ctx.bot.raid_info['raid_eggs']["5"]['pokemon'][0]).lower()
        description = f"**Marilla Park.**\n{tier5}\n**CP:** 60540 - **Moves:** Confusion / Shadow Ball\n*Raid Ending: 0 hours 46 min 50 sec*"
        url = "https://gymhuntr.com/#34.008618,-118.49125"
        img_url = 'https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/pkmn/150_.png?cache=1'
        huntrembed = discord.Embed(title=_('Level 5 Raid has started!'), description=description, url=url, colour=message.guild.me.colour)
        huntrembed.set_thumbnail(url=img_url)
        huntrmessage = await ctx.channel.send(embed=huntrembed)
        ctx = await self.bot.get_context(huntrmessage)
        await self.on_huntr(ctx)

    @commands.command(hidden=True)
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

    @commands.command(hidden=True)
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

    @commands.command(hidden=True)
    async def alarmrecover(self, ctx):
        message_list = []
        await utils.safe_delete(ctx.message)
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.channel.guild.id]['configure_dict']['settings']['offset'])
        async with ctx.channel.typing():
            async for message in ctx.channel.history(limit=500, oldest_first=False):
                if len(message_list) > 90:
                    await utils.safe_bulk_delete(ctx.channel, message_list)
                    message_list = []
                if message.content.lower().startswith('!alarm') and "{" in message.content and "}" in message.content:
                    message.content = message.content.replace("!alarm","").strip()
                    timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset']))
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

    @commands.command(hidden=True)
    @commands.has_permissions(manage_guild=True)
    async def alarmraid(self, ctx):
        """Simulates an alarm raid"""
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        await utils.safe_delete(message)
        tier5 = str(ctx.bot.raid_info['raid_eggs']["5"]['pokemon'][0]).lower()
        embed = discord.Embed(title="Title", description="Embed Description")
        huntrmessage = await ctx.channel.send('!alarm ' + str({"type":"raid", "pokemon":tier5, "gym":"Marilla Park", "gps":"39.628941,-79.935063", "moves":"Move 1 / Move 2", "raidexp":38}).replace("'", '"'), embed=embed)
        ctx = await self.bot.get_context(huntrmessage)
        await self.on_pokealarm(ctx)

    @commands.command(hidden=True)
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

    @commands.command(hidden=True)
    @commands.has_permissions(manage_guild=True)
    async def alarmwild(self, ctx):
        """Simulates an alarm wild"""
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        await utils.safe_delete(message)
        huntrmessage = await ctx.channel.send('!alarm {"type":"wild", "pokemon":"Pikachu", "gps":"39.645742,-79.96908", "expire":"5 min 0 sec", "iv_percent":"95.5", "iv_long":"14 / 14/ 15", "level":"27", "gender":"male", "height":"0.4", "weight":"6", "moveset":"Quick Attack / Wild Charge"}')
        ctx = await self.bot.get_context(huntrmessage)
        await self.on_pokealarm(ctx)

    @commands.command(hidden=True)
    @commands.has_permissions(manage_guild=True)
    async def alarmquest(self, ctx):
        """Simulates an alarm quest"""
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        await utils.safe_delete(message)
        huntrmessage = await ctx.channel.send('!alarm {"type":"research", "pokestop":"Marilla Park", "gps":"39.645742,-79.96908", "quest":"Catch 5 Electric Pokemon", "reward":"Pikachu Encounter"}')
        ctx = await self.bot.get_context(huntrmessage)
        await self.on_pokealarm(ctx)

    @commands.command(hidden=True)
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

    @commands.command(hidden=True)
    @commands.has_permissions(manage_guild=True)
    async def alarminv(self, ctx):
        """Simulates an alarm invasion"""
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        await utils.safe_delete(message)
        type_list = ["normal", "fighting", "flying", "poison", "ground", "rock", "bug", "ghost", "steel", "fire", "water", "grass", "electric", "psychic", "ice", "dragon", "dark", "fairy"]
        random_type = random.choice(type_list)
        huntrmessage = await ctx.channel.send('!alarm ' + str({"type":"invasion", "pokestop":"Marilla Park", "reward":random_type, "gps":"39.645742,-79.96908", "gender":"male", "expire":25}).replace("'", '"'))
        ctx = await self.bot.get_context(huntrmessage)
        await self.on_pokealarm(ctx)

def setup(bot):
    bot.add_cog(Huntr(bot))

def teardown(bot):
    bot.remove_cog(Huntr)
