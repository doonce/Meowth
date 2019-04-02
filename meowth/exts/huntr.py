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

import discord
from discord.ext import commands

import meowth
from meowth import checks
from meowth.exts import pokemon as pkmn_class
from meowth.exts import utilities as utils

logger = logging.getLogger("meowth")

class Huntr(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.event_loop = asyncio.get_event_loop()
        bot.loop.create_task(self.huntr_cleanup())

    async def huntr_cleanup(self, loop=True):
        while (not self.bot.is_closed()):
            await self.bot.wait_until_ready()
            logger.info('------ BEGIN ------')
            guilddict_temp = copy.deepcopy(self.bot.guild_dict)
            for guildid in guilddict_temp.keys():
                report_edit_dict = {}
                report_delete_dict = {}
                pokealarm_dict = guilddict_temp[guildid].get('pokealarm_dict', {})
                pokehuntr_dict = guilddict_temp[guildid].get('pokehuntr_dict', {})
                report_dict_dict = {
                    'pokealarm_dict':pokealarm_dict,
                    'pokehuntr_dict':pokehuntr_dict
                }
                for report_dict in report_dict_dict:
                    for reportid in report_dict_dict[report_dict].keys():
                        if report_dict_dict[report_dict][reportid].get('exp', 0) <= time.time():
                            report_channel = self.bot.get_channel(report_dict_dict[report_dict][reportid].get('reportchannel'))
                            if report_channel:
                                user_report = report_dict_dict[report_dict][reportid].get('reportmessage', None)
                                if user_report:
                                    report_delete_dict[user_report] = {"action":"delete", "channel":report_channel}
                                if report_dict_dict[report_dict][reportid].get('expedit') == "delete":
                                    report_delete_dict[reportid] = {"action":"delete", "channel":report_channel}
                                else:
                                    report_edit_dict[reportid] = {"action":report_dict_dict[report_dict][reportid]['expedit'], "channel":report_channel}
                                if report_dict_dict[report_dict][reportid].get('dm_dict', False):
                                    await utils.expire_dm_reports(self.bot, report_dict_dict[report_dict][reportid]['dm_dict'])
                            try:
                                del self.bot.guild_dict[guildid][report_dict][reportid]
                            except KeyError:
                                pass
                for messageid in report_delete_dict.keys():
                    try:
                        report_message = await report_delete_dict[messageid]['channel'].fetch_message(messageid)
                        await utils.safe_delete(report_message)
                    except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException, KeyError):
                        pass
                for messageid in report_edit_dict.keys():
                    try:
                        report_message = await report_edit_dict[messageid]['channel'].fetch_message(messageid)
                        await report_message.edit(content=report_edit_dict[messageid]['action']['content'], embed=discord.Embed(description=report_edit_dict[messageid]['action'].get('embedcontent'), colour=report_message.embeds[0].colour.value))
                        await report_message.clear_reactions()
                    except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException, IndexError, KeyError):
                        pass
            # save server_dict changes after cleanup
            logger.info('SAVING CHANGES')
            try:
                await self.bot.save()
            except Exception as err:
                logger.info('SAVING FAILED' + err)
            logger.info('------ END ------')
            if not loop:
                return
            await asyncio.sleep(600)
            continue

    """Handlers"""

    @commands.Cog.listener()
    async def on_message(self, message):
        ctx = await self.bot.get_context(message)
        if not ctx.guild:
            return
        if message.guild and (message.author.bot or message.webhook_id) and message.author != ctx.guild.me and ("!raid" in message.content or "!raidegg" in message.content or "!wild" in message.content or "!research" in message.content):
            await self.on_pokealarm(ctx)
        if message.guild and (message.author.bot or message.webhook_id or message.author.id in self.bot.config.get('managers', []) or message.author.id == self.bot.config['master']) and message.author != ctx.guild.me and "!alarm" in message.content:
            await self.on_pokealarm(ctx)
        if (str(message.author) == 'GymHuntrBot#7279') or (str(message.author) == 'HuntrBot#1845'):
            await self.on_huntr(ctx)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        channel = self.bot.get_channel(payload.channel_id)
        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.errors.NotFound, AttributeError, discord.Forbidden):
            return
        ctx = await self.bot.get_context(message)
        guild = message.guild
        try:
            user = guild.get_member(payload.user_id)
        except AttributeError:
            return
        pokealarm_dict = copy.deepcopy(ctx.bot.guild_dict[channel.guild.id].get('pokealarm_dict', {}))
        pokehuntr_dict = copy.deepcopy(ctx.bot.guild_dict[channel.guild.id].get('pokehuntr_dict', {}))
        if message.id in pokealarm_dict.keys() and not user.bot and str(payload.emoji) == self.bot.config['huntr_report']:
            await self.on_pokealarm(ctx, user)
        if message.id in pokehuntr_dict.keys() and not user.bot and str(payload.emoji) == self.bot.config['huntr_report']:
            await self.on_huntr(ctx, user)

    async def on_huntr(self, ctx, reactuser=None):
        message = ctx.message
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])).strftime('%I:%M %p')
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])
        auto_raid = self.bot.guild_dict[message.guild.id]['configure_dict']['scanners'].get('autoraid', False)
        auto_egg = self.bot.guild_dict[message.guild.id]['configure_dict']['scanners'].get('autoegg', False)
        auto_wild = self.bot.guild_dict[message.guild.id]['configure_dict']['scanners'].get('autowild', False)
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
                    channel_gps = self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid].get('gymhuntrgps', None)
                    channel_address = self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid].get('address', None)
                    if not channel_gps:
                        continue
                    if channel_gps == huntrgps or channel_address == raid_details:
                        channel = self.bot.get_channel(channelid)
                        if self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid]['type'] == 'egg':
                            await raid_cog._eggtoraid(entered_raid.lower().strip(), channel, author=message.author, huntr=moveset)
                        raidmsg = await channel.fetch_message(self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid]['raidmessage'])
                        if moveset and raidmsg.embeds[0].fields[2].name != moveset:
                            await channel.send(_("This {entered_raid}'s moves are: **{moves}**").format(entered_raid=entered_raid.title(), moves=moveset))
                        return
                if auto_report and reporttype == "raid":
                    await self.huntr_raid(ctx, entered_raid, raid_details, raidexp, huntrgps, moveset)
                elif auto_report and reporttype == "egg":
                    await self.huntr_raidegg(ctx, egg_level, raid_details, raidexp, huntrgps)
                elif reporttype == "raid":
                    raid_embed = await self.make_raid_embed(ctx, entered_raid, raid_details, raidexp, huntrgps, moveset)
                    raid = discord.utils.get(message.guild.roles, name=entered_raid.lower())
                    if raid == None:
                        roletest = ""
                    else:
                        roletest = _("{pokemon} - ").format(pokemon=raid.mention)
                    pokehuntr_dict = self.bot.guild_dict[message.guild.id].setdefault('pokehuntr_dict', {})
                    ctx.raidreport = await message.channel.send(content=_('{roletest}Meowth! {pokemon} raid reported by {member}! Details: {location_details}. React if you want to make a channel for this raid!').format(roletest=roletest, pokemon=entered_raid.title(), member=message.author.mention, location_details=raid_details), embed=raid_embed)
                    await asyncio.sleep(0.25)
                    await raidreport.add_reaction(self.bot.config['huntr_report'])
                    dm_dict = await raid_cog.send_dm_messages(ctx, raid_details, f"Meowth! {entered_raid.title()} raid reported by {message.author.display_name} in {message.channel.mention}! Details: {raid_details}. React in {message.channel.mention} to report this raid!", copy.deepcopy(raid_embed), dm_dict)
                    self.bot.guild_dict[message.guild.id]['pokehuntr_dict'][ctx.raidreport.id] = {
                        "exp":time.time() + (raidexp * 60),
                        'expedit': {"content":ctx.raidreport.content.split(" React")[0], "embedcontent":_('**This {pokemon} raid has expired!**').format(pokemon=entered_raid)},
                        "reporttype":"raid",
                        "reportchannel":message.channel.id,
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
                    raid_embed = await self.make_egg_embed(ctx, egg_level, raid_details, raidexp, huntrgps, reporter="huntr")
                    pokehuntr_dict = self.bot.guild_dict[message.guild.id].setdefault('pokehuntr_dict', {})
                    ctx.raidreport = await message.channel.send(content=_('Meowth! Level {level} raid egg reported by {member}! Details: {location_details}. React if you want to make a channel for this raid!').format(level=egg_level, member=message.author.mention, location_details=raid_details), embed=raid_embed)
                    await asyncio.sleep(0.25)
                    await raidreport.add_reaction(self.bot.config['huntr_report'])
                    dm_dict = await raid_cog.send_dm_messages(ctx, raid_details, f"Meowth! Level {egg_level} raid egg reported by {message.author.display_name} in {message.channel.mention}! Details: {raid_details}. React in {message.channel.mention} to report this raid!", copy.deepcopy(raid_embed), dm_dict)
                    self.bot.guild_dict[message.guild.id]['pokehuntr_dict'][ctx.raidreport.id] = {
                        "exp":time.time() + (int(raidexp) * 60),
                        'expedit': {"content":ctx.raidreport.content.split(" React")[0], "embedcontent": _('**This level {level} raid egg has hatched!**').format(level=egg_level)},
                        "reporttype":"egg",
                        "reportchannel":message.channel.id,
                        "level":egg_level,
                        "pokemon":None,
                        "reporttime":now,
                        "gym":raid_details,
                        "gps":huntrgps,
                        "embed":raid_embed
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
            gymhuntrgps = pokehuntr_dict[message.id]['gps']
            raid_details = pokehuntr_dict[message.id]['gym'].strip()
            dm_dict = copy.deepcopy(pokehuntr_dict[message.id]['dm_dict'])
            reacttime = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])
            timediff = relativedelta(reacttime, reporttime)
            raidexp = int(reporttime.minute) - int(timediff.minutes)
            if reporttype == "egg":
                egg_level = pokehuntr_dict[message.id]['level']
                raid_channel = await self.huntr_raidegg(ctx, egg_level, raid_details, raidexp, gymhuntrgps, report_user=reactuser, dm_dict=dm_dict)
            elif reporttype == "raid":
                entered_raid = pokehuntr_dict[message.id]['pokemon']
                gymhuntrmoves = pokehuntr_dict[message.id]['moves']
                raid_channel = await self.huntr_raid(ctx, entered_raid, raid_details, raidexp, gymhuntrgps, gymhuntrmoves, report_user=reactuser, dm_dict=dm_dict)
        return

    async def on_pokealarm(self, ctx, reactuser=None):
        """Requires a specific message.content format, which is "content" in PokeAlarm
        If an option is not available, replace <variable> with None
        Raid format = !raid <form> <pkmn>|<gym_name>|<time_left>|<lat>,<lng>|<quick_move> / <charge_move>
        Raidegg format = !raidegg <level>|<gym_name>|<time_left_start>|<lat>,<lng>
        Wild format = !wild <form> <pkmn>|<lat>,<lng>|<time_left>|Weather: <weather> / IV: <iv>
        I also recommend to set the username to just PokeAlarm"""
        message = ctx.message
        raid_channel = False
        pokealarm_dict = self.bot.guild_dict[ctx.guild.id].setdefault('pokealarm_dict', {})
        dm_dict = {}
        if not reactuser:
            reporttype = None
            report = None
            embed = message.embeds[0] if message.embeds else None
            now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])
            if "!raidegg" in message.content.lower():
                if not self.bot.guild_dict[message.guild.id]['configure_dict']['scanners'].get('autoegg', False):
                    return
                raid_cog = self.bot.cogs.get('Raid')
                if not raid_cog:
                    logger.error("Raid Cog not loaded")
                    return
                painfo = message.content.replace("!raidegg", "").strip().split("|")
                reporttype = "egg"
                gps = painfo[3]
                moves = None
                egg_level = painfo[0].replace("!raidegg", "").strip()
                entered_raid = None
                raidexp = painfo[2].split()[0][:-1]
                raid_details = painfo[1].strip()
                timeout = int(raidexp)*60
                expiremsg = ('This level {level} raid egg has hatched!').format(level=egg_level)
            elif "!raid" in message.content.lower():
                if not self.bot.guild_dict[message.guild.id]['configure_dict']['scanners'].get('autoraid', False):
                    return
                raid_cog = self.bot.cogs.get('Raid')
                if not raid_cog:
                    logger.error("Raid Cog not loaded")
                    return
                painfo = message.content.replace("!raid", "").strip().split("|")
                reporttype = "raid"
                gps = painfo[3]
                moves = painfo[4]
                entered_raid = painfo[0].lower().strip()
                pokemon = pkmn_class.Pokemon.get_pokemon(ctx.bot, entered_raid)
                if not pokemon:
                    return
                pokemon.gender = None
                pokemon.shiny = None
                entered_raid = str(pokemon)
                egg_level = 0
                raidexp = painfo[2].split()[0][:-1]
                raid_details = painfo[1].strip()
                timeout = int(raidexp)*60
                expiremsg = _('**This {pokemon} raid has expired!**').format(pokemon=entered_raid.title())
            elif "!wild" in message.content.lower():
                if not self.bot.guild_dict[message.guild.id]['configure_dict']['scanners'].get('autowild', False):
                    return
                wild_cog = self.bot.cogs.get('Wild')
                if not wild_cog:
                    logger.error("Wild Cog not loaded")
                    return
                painfo = message.content.replace("!wild2", "").strip().split("|")
                reporttype = "wild"
                exptime = painfo[2]
                #minutes = exptime.split()[0][:-1]
                minutes = "45"
                seconds = exptime.split()[1][:-1]
                huntrexp = "{min} min {sec} sec".format(min=minutes, sec=seconds)
                wild_extra = painfo[3]
                entered_wild = painfo[0].lower().strip()
                wild_details = painfo[1]
                location = f"https://www.google.com/maps/search/?api=1&query={wild_details}"
                despawn = (int(minutes) * 60) + int(seconds)
                alarm_details = {"pokemon":entered_wild, "coordinates":wild_details, "expire":huntrexp, "weather":wild_extra.split(" / ")[0].replace("Weather: ", ""), "iv_percent":wild_extra.split(" / IV: ")[1]}
            elif "!research" in message.content.lower():
                if not self.bot.guild_dict[message.guild.id]['configure_dict']['scanners'].get('autoquest', True):
                    return
                research_cog = self.bot.cogs.get('Research')
                if not research_cog:
                    logger.error("Research Cog not loaded")
                    return
                painfo = message.content.replace("!research", "").strip().split("|")
                reporttype = "quest"
                pokestop = painfo[0]
                gps = painfo[1]
                quest = painfo[2]
                reward = painfo[3]
            elif "!alarm" in message.content.lower():
                message.content = message.content.replace("!alarm","").strip()
                try:
                    alarm_details = json.loads(message.content)
                except:
                    return
                if alarm_details.get('type', None) == "wild":
                    if not self.bot.guild_dict[message.guild.id]['configure_dict']['scanners'].get('autowild', False):
                        return
                    wild_cog = self.bot.cogs.get('Wild')
                    if not wild_cog:
                        logger.error("Wild Cog not loaded")
                        return
                    reporttype = "wild"
                    pokemon = alarm_details.setdefault('pokemon', None)
                    coordinates = alarm_details.setdefault("coordinates", None)
                    if not pokemon or not coordinates:
                        return
                    await utils.safe_delete(message)
                    await self.huntr_wild(ctx, alarm_details)
                    return
            else:
                return
            await utils.safe_delete(message)
            if reporttype == "wild":
                await self.huntr_wild(ctx, alarm_details)
                return
            if reporttype == "quest":
                await self.huntr_research(ctx, pokestop, gps, quest, reward)
                return
            else:
                for channelid in self.bot.guild_dict[message.guild.id]['raidchannel_dict']:
                    channel_gps = self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid].get('gymhuntrgps', None)
                    channel_address = self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid].get('address', None)
                    channel_level = self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid].get('egglevel', None)
                    channel_type = self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid].get('type', None)
                    if channel_level == "EX":
                        continue
                    if channel_gps == gps or channel_address == raid_details:
                        channel = self.bot.get_channel(channelid)
                        if embed and channel:
                            await channel.send(embed=embed)
                        if channel_type == 'egg':
                            if not utils.get_level(self.bot, entered_raid):
                                logger.error(f"{entered_raid} not in raid_json")
                                return
                            await raid_cog._eggtoraid(entered_raid, channel, message.author, huntr=moves)
                        elif channel and moves:
                            await channel.send(_("This {entered_raid}'s moves are: **{moves}**").format(entered_raid=entered_raid.title(), moves=moves))
                            try:
                                raid_msg = await channel.fetch_message(self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid]['raidmessage'])
                            except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                                return
                            raid_embed = raid_msg.embeds[0]
                            for field in raid_embed.fields:
                                if "moveset" in field.name.lower():
                                    return
                            raid_embed.add_field(name="**Moveset**:", value=moves, inline=True)
                            await raid_msg.edit(embed=raid_embed)
                        await self.auto_counters(channel, moves)
                        return
                if reporttype == "egg":
                    if int(egg_level) in self.bot.guild_dict[message.guild.id]['configure_dict']['scanners'].get('egglvls', False):
                        raid_channel = await self.huntr_raidegg(ctx, egg_level, raid_details, raidexp, gps)
                        if embed and raid_channel:
                            await raid_channel.send(embed=embed)
                        return
                    else:
                        raidmsg = f"Meowth! Level {egg_level} raid egg reported by {message.author.mention}! Details: {raid_details}. React with {self.bot.config['huntr_report']} if you want to make a channel for this egg!"
                        ctx.raidreport = await message.channel.send(raidmsg, embed=embed)
                        dm_dict = await raid_cog.send_dm_messages(ctx, raid_details, f"Meowth! Level {egg_level} raid egg reported by {message.author.display_name} in {message.channel.mention}! Details: {raid_details}. React in {message.channel.mention} to report this raid!", copy.deepcopy(embed), dm_dict)
                elif reporttype == "raid":
                    if not utils.get_level(self.bot, entered_raid):
                        logger.error(f"{entered_raid} not in raid_json")
                        return
                    if int(utils.get_level(self.bot, entered_raid)) in self.bot.guild_dict[message.guild.id]['configure_dict']['scanners'].get('raidlvls', []):
                        raid_channel = await self.huntr_raid(ctx, entered_raid, raid_details, raidexp, gps, moves)
                        if embed and raid_channel:
                            await raid_channel.send(embed=embed)
                        return
                    else:
                        raid = discord.utils.get(message.guild.roles, name=pokemon.name.lower())
                        if raid == None:
                            roletest = ""
                        else:
                            roletest = _("{pokemon} - ").format(pokemon=raid.mention)
                        raidmsg = f"{roletest}Meowth! {entered_raid.title()} raid reported by {message.author.mention}! Details: {raid_details}. React with {self.bot.config['huntr_report']} if you want to make a channel for this raid!"
                        ctx.raidreport = await message.channel.send(raidmsg, embed=embed)
                        dm_dict = await raid_cog.send_dm_messages(ctx, raid_details, f"Meowth! {entered_raid.title()} raid reported by {message.author.display_name} in {message.channel.mention}! Details: {raid_details}. React in {message.channel.mention} to report this raid!", copy.deepcopy(embed), dm_dict)
                self.bot.guild_dict[message.guild.id]['pokealarm_dict'][ctx.raidreport.id] = {
                    "exp":time.time() + timeout,
                    'expedit': {"content":raidmsg.split("React")[0], "embedcontent":expiremsg},
                    "reporttype":reporttype,
                    "reportchannel":message.channel.id,
                    "level":egg_level,
                    "pokemon":entered_raid,
                    "gps":gps,
                    "gym":raid_details,
                    "raidexp":raidexp,
                    "reporttime":now,
                    "moves":moves,
                    "embed":embed,
                    "dm_dict":dm_dict
                }
                await asyncio.sleep(0.25)
                await ctx.raidreport.add_reaction(self.bot.config['huntr_report'])
        else:
            await utils.safe_delete(message)
            pokealarm_dict = copy.deepcopy(self.bot.guild_dict[message.guild.id].get('pokealarm_dict', {}))
            alarm_details = pokealarm_dict[message.id]
            embed = alarm_details['embed']
            reporttime = alarm_details['reporttime']
            reporttype = alarm_details['reporttype']
            huntrtime = alarm_details['raidexp']
            dm_dict = copy.deepcopy(alarm_details['dm_dict'])
            reacttime = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])
            timediff = relativedelta(reacttime, reporttime)
            exptime = int(huntrtime) - int(timediff.minutes)
            if reporttype == "egg":
                raid_channel = await self.huntr_raidegg(ctx, alarm_details['level'], alarm_details['gym'], exptime, alarm_details['gps'], report_user=reactuser, dm_dict=dm_dict)
            elif reporttype == "raid":
                raid_channel = await self.huntr_raid(ctx, alarm_details['pokemon'], alarm_details['gym'], exptime, alarm_details['gps'], alarm_details['moves'], report_user=reactuser, dm_dict=dm_dict)
            if embed and raid_channel:
                await raid_channel.send(embed=embed)

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

    async def make_egg_embed(self, ctx, egg_level, raid_details, raidexp, gymhuntrgps, reporter=None):
        message = ctx.message
        timestamp = (message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])).strftime(_('%I:%M %p (%H:%M)'))
        raid_gmaps_link = f"https://www.google.com/maps/search/?api=1&query={gymhuntrgps}"
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        gym_info = ""
        if gym_matching_cog:
            gym_info, raid_details, gym_url = await gym_matching_cog.get_gym_info(ctx, raid_details, "raid")
            if gym_url:
                raid_gmaps_link = gym_url
        if not raid_details:
            return
        egg_level = str(egg_level)
        egg_info = ctx.bot.raid_info['raid_eggs'][egg_level]
        egg_img = egg_info['egg_img']
        boss_list = []
        for p in egg_info['pokemon']:
            pokemon = pkmn_class.Pokemon.get_pokemon(ctx.bot, p)
            boss_list.append(pokemon.name.title() + ' (' + str(pokemon.id) + ') ' + pokemon.emoji)
        raid_img_url = 'https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/eggs/{}?cache=1'.format(str(egg_img))
        raid_embed = discord.Embed(title=_('Meowth! Click here for directions to the coming level {level} raid!').format(level=egg_level), description=gym_info, url=raid_gmaps_link, colour=message.guild.me.colour)
        if len(egg_info['pokemon']) > 1:
            raid_embed.add_field(name=_('**Possible Bosses:**'), value=_('{bosslist1}').format(bosslist1='\n'.join(boss_list[::2])), inline=True)
            raid_embed.add_field(name='\u200b', value=_('{bosslist2}').format(bosslist2='\n'.join(boss_list[1::2])), inline=True)
        else:
            raid_embed.add_field(name=_('**Possible Bosses:**'), value=_('{bosslist}').format(bosslist=''.join(boss_list)), inline=True)
            raid_embed.add_field(name='\u200b', value='\u200b', inline=True)
        raid_embed.add_field(name=_('**Next Group:**'), value=_('Set with **!starttime**'), inline=True)
        raid_embed.add_field(name=_('**Hatches:**'), value=_('Set with **!timerset**'), inline=True)
        if reporter == "huntr":
            raid_embed.add_field(name="\u200b", value=_("Perform a scan to help find more by clicking [here](https://gymhuntr.com/#{huntrurl}).").format(huntrurl=gymhuntrgps), inline=False)
        raid_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=message.author.display_name, timestamp=timestamp), icon_url=message.author.avatar_url_as(format=None, static_format='jpg', size=32))
        raid_embed.set_thumbnail(url=raid_img_url)
        return raid_embed

    async def make_raid_embed(self, ctx, entered_raid, raid_details, raidexp, gymhuntrgps, gymhuntrmoves=None, reporter=None):
        message = ctx.message
        timestamp = (message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])).strftime(_('%I:%M %p (%H:%M)'))
        raid_gmaps_link = f"https://www.google.com/maps/search/?api=1&query={gymhuntrgps}"
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        pokemon = pkmn_class.Pokemon.get_pokemon(ctx.bot, entered_raid)
        if pokemon:
            entered_raid = pokemon.name.lower()
            pokemon.shiny = False
            pokemon.gender = False
        level = utils.get_level(ctx.bot, pokemon.id)
        gym_info = ""
        if gym_matching_cog:
            gym_info, raid_details, gym_url = await gym_matching_cog.get_gym_info(ctx, raid_details, "raid")
            if gym_url:
                raid_gmaps_link = gym_url
        if not raid_details:
            await utils.safe_delete(ctx.message)
            return
        raid = discord.utils.get(message.guild.roles, name=entered_raid)
        if raid == None:
            roletest = ""
        else:
            roletest = _("{pokemon} - ").format(pokemon=raid.mention)
        raid_number = pokemon.id
        raid_embed = discord.Embed(title=_('Meowth! Click here for directions to the level {level} raid!').format(level=level), description=gym_info, url=raid_gmaps_link, colour=message.guild.me.colour)
        raid_embed.add_field(name=_('**Details:**'), value=_('{pokemon} ({pokemonnumber}) {type}').format(pokemon=pokemon.name.title(), pokemonnumber=pokemon.id, type=pokemon.emoji), inline=True)
        raid_embed.add_field(name=_('**Weaknesses:**'), value=_('{weakness_list}').format(weakness_list=utils.weakness_to_str(ctx.bot, message.guild, utils.get_weaknesses(ctx.bot, pokemon.name.lower(), pokemon.form, pokemon.alolan))), inline=True)
        raid_embed.add_field(name=_('**Next Group:**'), value=_('Set with **!starttime**'), inline=True)
        raid_embed.add_field(name=_('**Expires:**'), value=_('Set with **!timerset**'), inline=True)
        if gymhuntrmoves:
            raid_embed.add_field(name=_("**Moveset:**"), value=gymhuntrmoves)
        raid_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=message.author.display_name, timestamp=timestamp), icon_url=message.author.avatar_url_as(format=None, static_format='jpg', size=32))
        raid_embed.set_thumbnail(url=pokemon.img_url)
        return raid_embed

    """Reporting"""

    async def huntr_wild(self, ctx, report_details, reporter=None, report_user=None, dm_dict=None):
        if not dm_dict:
            dm_dict = {}
        if report_user:
            ctx.message.author = report_user
        message = ctx.message
        timestamp = (message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])).strftime(_('%I:%M %p (%H:%M)'))
        pokemon = pkmn_class.Pokemon.get_pokemon(ctx.bot, report_details['pokemon'])
        if pokemon:
            entered_wild = pokemon.name.lower()
            pokemon.shiny = False
        else:
            return
        if pokemon.id in ctx.bot.guild_dict[message.channel.guild.id]['configure_dict']['scanners'].setdefault('wildfilter', []):
            return
        details_str = f"{pokemon.name.title()}"
        gender = report_details.get("gender", '')
        if gender and "male" in gender.lower():
            details_str += f" (♂)"
        elif gender and "female" in gender.lower():
            details_str += f" (♀)"
        details_str += f" ({pokemon.id}) {pokemon.emoji}"
        wild_details = report_details['coordinates']
        wild_iv = report_details.get("iv_percent", '')
        iv_long = report_details.get("iv_long", '')
        if wild_iv:
            if utils.is_number(wild_iv) and float(wild_iv) >= 0 and float(wild_iv) <= 100:
                wild_iv = int(round(float(wild_iv)))
            else:
                wild_iv = None
        if wild_iv or wild_iv == 0:
            iv_str = f" - **{wild_iv}IV**"
        else:
            iv_str = ""
        level = str(report_details.get("level", ''))
        cp = str(report_details.get("cp", ''))
        weather = report_details.get("weather", '')
        if weather.lower() == 'none':
            weather = ''
        height = report_details.get("height", '')
        weight = report_details.get("weight", '')
        moveset = report_details.get("moveset", '')
        expire = report_details.get("expire", "45 min 00 sec")
        huntrexpstamp = (message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'], minutes=int(expire.split()[0]), seconds=int(expire.split()[2]))).strftime('%I:%M %p')
        nearest_stop = ""
        wild_cog = self.bot.get_cog("Wild")
        wild_types = copy.deepcopy(pokemon.types)
        wild_types.append('None')
        expiremsg = _('**This {pokemon} has despawned!**').format(pokemon=entered_wild.title())
        if reporter == "huntr":
            wild_coordinates = wild_details.split("#")[1]
        else:
            wild_coordinates = wild_details
        wild_gmaps_link = f"https://www.google.com/maps/search/?api=1&query={wild_coordinates}"
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        if gym_matching_cog:
            nearest_stop = gym_matching_cog.find_nearest_stop((wild_coordinates.split(",")[0],wild_coordinates.split(",")[1]), message.guild.id)
            if nearest_stop:
                wild_details = nearest_stop
        wild_embed = discord.Embed(description="", title=_('Meowth! Click here for exact directions to the wild {pokemon}!').format(pokemon=entered_wild.title()), url=wild_gmaps_link, colour=message.guild.me.colour)
        wild_embed.add_field(name=_('**Details:**'), value=details_str, inline=True)
        if iv_long or wild_iv or level or cp or weather:
            wild_embed.add_field(name=_('**IV / Level:**'), value=f"{iv_long if iv_long else ''} {' ('+str(wild_iv)+'%)' if wild_iv else ''}\n{'Level '+level if level else ''}{' ('+cp+'CP)' if cp else ''} {weather if weather else ''}", inline=True)
        if height or weight or moveset:
            wild_embed.add_field(name=_('**Other Info:**'), value=f"{'H: '+height if height else ''} {'W: '+weight if weight else ''}\n{moveset if moveset else ''}", inline=True)
        wild_embed.add_field(name='**Despawns in:**', value=_('{huntrexp} mins ({huntrexpstamp})').format(huntrexp=expire.split()[0], huntrexpstamp=huntrexpstamp), inline=True)
        if reporter == "huntr":
            wild_embed.add_field(name=wild_extra, value=_('Perform a scan to help find more by clicking [here]({huntrurl}).').format(huntrurl=wild_details), inline=False)
        wild_embed.set_thumbnail(url=pokemon.img_url)
        wild_embed.add_field(name='**Reactions:**', value=_("{emoji}: I'm on my way!").format(emoji=ctx.bot.config['wild_omw']), inline=True)
        wild_embed.add_field(name='\u200b', value=_("{emoji}: The Pokemon despawned!").format(emoji=ctx.bot.config['wild_despawn']), inline=True)
        wild_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=message.author.display_name, timestamp=timestamp), icon_url=message.author.avatar_url_as(format=None, static_format='jpg', size=32))
        despawn = (int(expire.split(' ')[0]) * 60) + int(expire.split(' ')[2])
        if nearest_stop:
            ctx.wildreportmsg = await message.channel.send(content=_('Meowth! Wild {pokemon} reported by {member}! Nearest Pokestop: {nearest_stop} | Coordinates: {location_details}{iv_str}').format(pokemon=str(pokemon).title(), member=message.author.mention, nearest_stop=nearest_stop, location_details=wild_coordinates, iv_str=iv_str), embed=wild_embed)
        else:
            ctx.wildreportmsg = await message.channel.send(content=_('Meowth! Wild {pokemon} reported by {member}! Coordinates: {location_details}{iv_str}').format(pokemon=str(pokemon).title(), member=message.author.mention, location_details=wild_coordinates, iv_str=iv_str), embed=wild_embed)
        dm_dict = await wild_cog.send_dm_messages(ctx, pokemon.id, wild_details, wild_types[0], wild_types[1], wild_iv, ctx.wildreportmsg.content.replace(ctx.author.mention, f"{ctx.author.display_name} in {ctx.channel.mention}"), wild_embed.copy(), dm_dict)
        await asyncio.sleep(0.25)
        await ctx.wildreportmsg.add_reaction(ctx.bot.config['wild_omw'])
        await asyncio.sleep(0.25)
        await ctx.wildreportmsg.add_reaction(ctx.bot.config['wild_despawn'])
        await asyncio.sleep(0.25)
        ctx.bot.guild_dict[message.guild.id]['wildreport_dict'][ctx.wildreportmsg.id] = {
            'exp':time.time() + despawn,
            'expedit': {"content":ctx.wildreportmsg.content, "embedcontent":expiremsg},
            'reportmessage':message.id,
            'reportchannel':message.channel.id,
            'reportauthor':message.author.id,
            'dm_dict':dm_dict,
            'location':wild_details,
            'gps':wild_coordinates,
            'url':wild_gmaps_link,
            'pokemon':entered_wild,
            'pkmn_obj':str(pokemon),
            'wild_iv':wild_iv,
            'omw':[]
        }

    async def huntr_raid(self, ctx, entered_raid, raid_details, raidexp, gymhuntrgps, gymhuntrmoves, reporter=None, report_user=None, dm_dict=None):
        if not dm_dict:
            dm_dict = {}
        raid_cog = self.bot.cogs.get('Raid')
        if report_user:
            ctx.message.author = report_user
        message = ctx.message
        timestamp = (message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])).strftime(_('%I:%M %p (%H:%M)'))
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])
        pokemon = pkmn_class.Pokemon.get_pokemon(ctx.bot, entered_raid)
        if pokemon:
            entered_raid = pokemon.name.lower()
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
        for boss in ctx.bot.raid_info['raid_eggs'][str(level)]['pokemon']:
            boss = pkmn_class.Pokemon.get_pokemon(ctx.bot, boss)
            if boss.id == pokemon.id:
                pokemon = boss
                entered_raid = boss.name.lower()
        weather = ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'].get(message.channel.id, {}).get('weather', None)
        raid_embed = await self.make_raid_embed(ctx, str(pokemon), raid_details, raidexp, gymhuntrgps, gymhuntrmoves)
        raid_channel = await raid_cog.create_raid_channel(ctx, entered_raid, raid_details, "raid")
        if not raid_channel:
            return
        await asyncio.sleep(1)
        ctx.raidreport = await message.channel.send(content=_('Meowth! {pokemon} raid reported by {member}! Details: {location_details}. Coordinate in {raid_channel}').format(pokemon=str(pokemon).title(), member=message.author.mention, location_details=raid_details, raid_channel=raid_channel.mention), embed=raid_embed)
        raid = discord.utils.get(message.guild.roles, name=pokemon.name.lower())
        if raid == None:
            roletest = ""
        else:
            roletest = _("{pokemon} - ").format(pokemon=raid.mention)
        raidmsg = _("{roletest}Meowth! {pokemon} raid reported by {member} in {citychannel}! Details: {location_details}. Coordinate here!\n\nClick the question mark reaction to get help on the commands that work in here.\n\nThis channel will be deleted five minutes after the timer expires.").format(roletest=roletest, pokemon=str(pokemon).title(), member=message.author.mention, citychannel=message.channel.mention, location_details=raid_details)
        raidmessage = await raid_channel.send(content=raidmsg, embed=raid_embed)
        await raidmessage.add_reaction('\u2754')
        await raidmessage.pin()
        level = utils.get_level(self.bot, entered_raid)
        ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid_channel.id] = {
            'reportcity': message.channel.id,
            'trainer_dict': {},
            'exp': time.time() + (60 * ctx.bot.raid_info['raid_eggs'][str(level)]['raidtime']),
            'manual_timer': False,
            'active': True,
            'raidmessage': raidmessage.id,
            'raidreport': ctx.raidreport.id,
            'reportmessage': message.id,
            'address': raid_details,
            'type': 'raid',
            'pokemon': entered_raid,
            'pkmn_obj': str(pokemon),
            'egglevel': '0',
            'moveset': 0,
            'weather': weather,
            'gymhuntrgps' : gymhuntrgps
        }
        await raid_cog._timerset(raid_channel, raidexp)
        await raid_channel.send("This raid was reported by a bot. If it is a duplicate of a raid already reported by a human, I can delete it with three **!duplicate** messages.")
        ctrs_dict = await raid_cog._get_generic_counters(message.guild, entered_raid, weather)
        if str(level) in ctx.bot.guild_dict[message.guild.id]['configure_dict']['counters']['auto_levels']:
            try:
                ctrsmsg = "Here are the best counters for the raid boss in currently known weather conditions! Update weather with **!weather**. If you know the moveset of the boss, you can react to this message with the matching emoji and I will update the counters."
                ctrsmessage = await raid_channel.send(content=ctrsmsg, embed=ctrs_dict[0]['embed'])
                ctrsmessage_id = ctrsmessage.id
                await ctrsmessage.pin()
                for moveset in ctrs_dict:
                    await ctrsmessage.add_reaction(ctrs_dict[moveset]['emoji'])
                    await asyncio.sleep(0.25)
            except:
                ctrsmessage_id = None
        else:
            ctrsmessage_id = None
        ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid_channel.id]['ctrsmessage'] = ctrsmessage_id
        ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid_channel.id]['ctrs_dict'] = ctrs_dict
        self.event_loop.create_task(raid_cog.expiry_check(raid_channel))
        raid_embed.remove_field(2)
        raid_embed.remove_field(2)
        self.bot.loop.create_task(raid_cog.edit_dm_messages(ctx, ctx.raidreport.content, copy.deepcopy(raid_embed), dm_dict))
        dm_dict = await raid_cog.send_dm_messages(ctx, raid_details, ctx.raidreport.content.replace(ctx.author.mention, f"{ctx.author.display_name} in {ctx.channel.mention}"), copy.deepcopy(raid_embed), dm_dict)
        ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid_channel.id]['dm_dict'] = dm_dict
        if report_user:
            raid_reports = self.bot.guild_dict[message.guild.id].setdefault('trainers', {}).setdefault(report_user.id, {}).setdefault('raid_reports', 0) + 1
            self.bot.guild_dict[message.guild.id]['trainers'][report_user.id]['raid_reports'] = raid_reports
        await self.auto_counters(raid_channel, gymhuntrmoves)
        return raid_channel

    async def huntr_raidegg(self, ctx, egg_level, raid_details, raidexp, gymhuntrgps, reporter=None, report_user=None, dm_dict=None):
        if not dm_dict:
            dm_dict = {}
        raid_cog = self.bot.cogs.get('Raid')
        if report_user:
            ctx.message.author = report_user
        message = ctx.message
        timestamp = (message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])).strftime(_('%I:%M %p (%H:%M)'))
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])
        weather = ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'].get(message.channel.id, {}).get('weather', None)
        raid_embed = await self.make_egg_embed(ctx, egg_level, raid_details, raidexp, gymhuntrgps, reporter)
        raid_channel = await raid_cog.create_raid_channel(ctx, egg_level, raid_details, "egg")
        if not raid_channel:
            return
        await asyncio.sleep(1)
        ctx.raidreport = await message.channel.send(content=_('Meowth! Level {level} raid egg reported by {member}! Details: {location_details}. Coordinate in {raid_channel}').format(level=egg_level, member=message.author.mention, location_details=raid_details, raid_channel=raid_channel.mention), embed=raid_embed)
        raidmsg = _("Meowth! Level {level} raid egg reported by {member} in {citychannel}! Details: {location_details}. Coordinate here!\n\nClick the question mark reaction to get help on the commands that work in here.\n\nThis channel will be deleted five minutes after the timer expires.").format(level=egg_level, member=message.author.mention, citychannel=message.channel.mention, location_details=raid_details)
        raidmessage = await raid_channel.send(content=raidmsg, embed=raid_embed)
        await raidmessage.add_reaction('\u2754')
        await raidmessage.pin()
        ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid_channel.id] = {
            'reportcity': message.channel.id,
            'trainer_dict': {},
            'exp': time.time() + (60 * ctx.bot.raid_info['raid_eggs'][egg_level]['hatchtime']),
            'manual_timer': False,
            'active': True,
            'raidmessage': raidmessage.id,
            'raidreport': ctx.raidreport.id,
            'reportmessage': message.id,
            'address': raid_details,
            'type': 'egg',
            'pokemon': '',
            'egglevel': egg_level,
            'weather': weather,
            'moveset': 0,
            'gymhuntrgps' : gymhuntrgps
        }
        if raidexp is not False:
            await raid_cog._timerset(raid_channel, raidexp)
        else:
            await raid_channel.send(content=_('Meowth! Hey {member}, if you can, set the time left until the egg hatches using **!timerset <minutes>** so others can check it with **!timer**.').format(member=message.author.mention))
        await raid_channel.send("This egg was reported by a bot. If it is a duplicate of a raid already reported by a human, I can delete it with three **!duplicate** messages.")
        if len(ctx.bot.raid_info['raid_eggs'][egg_level]['pokemon']) == 1:
            pokemon = pkmn_class.Pokemon.get_pokemon(ctx.bot, ctx.bot.raid_info['raid_eggs'][egg_level]['pokemon'][0])
            pokemon = pokemon.name.lower()
            await raid_cog._eggassume(ctx, 'assume ' + pokemon, raid_channel)
        elif egg_level == "5" and ctx.bot.guild_dict[raid_channel.guild.id]['configure_dict']['settings'].get('regional', None) in ctx.bot.raid_list:
            pokemon = pkmn_class.Pokemon.get_pokemon(ctx.bot, ctx.bot.guild_dict[raid_channel.guild.id]['configure_dict']['settings']['regional'])
            pokemon = pokemon.name.lower()
            await raid_cog._eggassume(ctx, 'assume ' + pokemon, raid_channel)
        self.event_loop.create_task(raid_cog.expiry_check(raid_channel))
        raid_embed.remove_field(2)
        raid_embed.remove_field(2)
        self.bot.loop.create_task(raid_cog.edit_dm_messages(ctx, ctx.raidreport.content, copy.deepcopy(raid_embed), dm_dict))
        dm_dict = await raid_cog.send_dm_messages(ctx, raid_details, ctx.raidreport.content.replace(ctx.author.mention, f"{ctx.author.display_name} in {ctx.channel.mention}"), copy.deepcopy(raid_embed), dm_dict)
        ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid_channel.id]['dm_dict'] = dm_dict
        if report_user:
            egg_reports = self.bot.guild_dict[message.guild.id].setdefault('trainers', {}).setdefault(report_user.id, {}).setdefault('egg_reports', 0) + 1
            self.bot.guild_dict[message.guild.id]['trainers'][report_user.id]['egg_reports'] = egg_reports
        return raid_channel

    async def huntr_research(self, ctx, location, gps, quest, reward):
        message = ctx.message
        channel = message.channel
        author = message.author
        guild = message.guild
        research_cog = self.bot.cogs.get('Research')
        nearest_stop = ""
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset']))
        to_midnight = 24*60*60 - ((timestamp-timestamp.replace(hour=0, minute=0, second=0, microsecond=0)).seconds)
        loc_url = f"https://www.google.com/maps/search/?api=1&query={gps}"
        research_embed = discord.Embed(description="", colour=message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/field-research.png?cache=1')
        research_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        pokemon = False
        reward_list = ["ball", "nanab", "pinap", "razz", "berr", "stardust", "potion", "revive", "candy"]
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        stop_info = ""
        if gym_matching_cog:
            nearest_stop = gym_matching_cog.find_nearest_stop((gps.split(",")[0],gps.split(",")[1]), guild.id)
            if nearest_stop:
                location = nearest_stop
            stop_info, location, stop_url = await gym_matching_cog.get_stop_info(ctx, location)
            if stop_url:
                loc_url = stop_url
        if not location:
            return
        research_embed.add_field(name=_("**Pokestop:**"), value='\n'.join(textwrap.wrap(string.capwords(location, ' '), width=30)), inline=True)
        research_embed.add_field(name=_("**Quest:**"), value='\n'.join(textwrap.wrap(string.capwords(quest, ' '), width=30)), inline=True)
        other_reward = any(x in reward.lower() for x in reward_list)
        pokemon = pkmn_class.Pokemon.get_pokemon(self.bot, reward, allow_digits=False)
        if pokemon and not other_reward:
            reward = f"{string.capwords(reward, ' ')} {pokemon.emoji}"
            research_embed.add_field(name=_("**Reward:**"), value=reward, inline=True)
        else:
            research_embed.add_field(name=_("**Reward:**"), value='\n'.join(textwrap.wrap(string.capwords(reward, ' '), width=30)), inline=True)
        await research_cog.send_research(ctx, research_embed, location, quest, reward, other_reward, loc_url)

    @commands.command(hidden=True)
    @commands.has_permissions(manage_guild=True)
    async def huntrraid(self, ctx):
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
    @commands.has_permissions(manage_guild=True)
    async def alarmraid(self, ctx):
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        await utils.safe_delete(message)
        tier5 = str(ctx.bot.raid_info['raid_eggs']["5"]['pokemon'][0]).lower()
        huntrmessage = await ctx.channel.send(f"!raid {tier5}|Marilla Park|38m 00s|34.008618,-118.49125|Move 1 / Move 2")
        ctx = await self.bot.get_context(huntrmessage)
        await self.on_pokealarm(ctx)

    @commands.command(hidden=True)
    @commands.has_permissions(manage_guild=True)
    async def alarmegg(self, ctx):
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        await utils.safe_delete(message)
        huntrmessage = await ctx.channel.send(f"!raidegg 2|Marilla Park|38m 00s|34.008618,-118.49125")
        ctx = await self.bot.get_context(huntrmessage)
        await self.on_pokealarm(ctx)

    @commands.command(hidden=True)
    @commands.has_permissions(manage_guild=True)
    async def alarmwild(self, ctx):
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        await utils.safe_delete(message)
        huntrmessage = await ctx.channel.send("!wild Weedle|39.645742,-79.969087|19m 00s|Weather: None / IV: None")
        ctx = await self.bot.get_context(huntrmessage)
        await self.on_pokealarm(ctx)

    @commands.command(hidden=True)
    @commands.has_permissions(manage_guild=True)
    async def alarmquest(self, ctx):
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        await utils.safe_delete(message)
        huntrmessage = await ctx.channel.send("!research Marilla Park|34.008618,-118.49125|Catch 5 Pokemon Category Pokémon|Pikachu Encounter")
        ctx = await self.bot.get_context(huntrmessage)
        await self.on_pokealarm(ctx)

def setup(bot):
    bot.add_cog(Huntr(bot))
