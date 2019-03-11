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

import discord
from discord.ext import commands

import meowth
from meowth import utils, checks
from meowth.exts import pokemon as pkmn_class

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
                        report_message = await report_delete_dict[messageid]['channel'].get_message(messageid)
                        await utils.safe_delete(report_message)
                    except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException, KeyError):
                        pass
                for messageid in report_edit_dict.keys():
                    try:
                        report_message = await report_edit_dict[messageid]['channel'].get_message(messageid)
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
        if (str(message.author) == 'GymHuntrBot#7279') or (str(message.author) == 'HuntrBot#1845'):
            await self.on_huntr(ctx)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        channel = self.bot.get_channel(payload.channel_id)
        try:
            message = await channel.get_message(payload.message_id)
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
                    raid_details = match.group(1)
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
                    raid_details = match.group(1)
                    raidexp = match.group(3)
                    entered_raid = None
                    moveset = False
                    await utils.safe_delete(message)
                    auto_report = True if int(ghegglevel) in self.bot.guild_dict[message.guild.id]['configure_dict']['scanners']['egglvls'] else False
                for channelid in self.bot.guild_dict[message.guild.id]['raidchannel_dict']:
                    channel_gps = self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid].get('gymhuntrgps', None)
                    channel_address = self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid].get('address', None)
                    if not channel_gps:
                        continue
                    if channel_gps == huntrgps or channel_address == raid_details:
                        channel = self.bot.get_channel(channelid)
                        if self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid]['type'] == 'egg':
                            await raid_cog._eggtoraid(ghpokeid.lower().strip(), channel, author=message.author, huntr=moveset)
                        raidmsg = await channel.get_message(self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid]['raidmessage'])
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
                    raidreport = await message.channel.send(content=_('{roletest}Meowth! {pokemon} raid reported by {member}! Details: {location_details}. React if you want to make a channel for this raid!').format(roletest=roletest, pokemon=entered_raid.title(), member=message.author.mention, location_details=raid_details), embed=raid_embed)
                    await asyncio.sleep(0.25)
                    await raidreport.add_reaction(self.bot.config['huntr_report'])
                    self.bot.guild_dict[message.guild.id]['pokehuntr_dict'][raidreport.id] = {
                        "exp":time.time() + (raidexp * 60),
                        'expedit': {"content":raidreport.content.split(" React")[0], "embedcontent":_('**This {pokemon} raid has expired!**').format(pokemon=entered_raid)},
                        "reporttype":"raid",
                        "reportchannel":message.channel.id,
                        "level":0,
                        "pokemon":entered_raid,
                        "reporttime":now,
                        "gym":raid_details,
                        "gps":huntrgps,
                        "moves":moveset,
                        "embed":raid_embed
                    }
                elif reporttype == "egg":
                    raid_embed = await self.make_egg_embed(ctx, egg_level, raid_details, raidexp, huntrgps, reporter="huntr")
                    pokehuntr_dict = self.bot.guild_dict[message.guild.id].setdefault('pokehuntr_dict', {})
                    raidreport = await message.channel.send(content=_('Meowth! Level {level} raid egg reported by {member}! Details: {location_details}. React if you want to make a channel for this raid!').format(level=egg_level, member=message.author.mention, location_details=raid_details), embed=raid_embed)
                    await asyncio.sleep(0.25)
                    await raidreport.add_reaction(self.bot.config['huntr_report'])
                    self.bot.guild_dict[message.guild.id]['pokehuntr_dict'][raidreport.id] = {
                        "exp":time.time() + (int(raidexp) * 60),
                        'expedit': {"content":raidreport.content.split(" React")[0], "embedcontent": _('**This level {level} raid egg has hatched!**').format(level=egg_level)},
                        "reporttype":"egg",
                        "reportchannel":message.channel.id,
                        "level":egg_level,
                        "pokemon":None,
                        "reporttime":now,
                        "gym":raid_details,
                        "gps":huntrgps,
                        "embed":raid_embed
                    }
            if (message.author.id == 295116861920772098) and message.embeds and auto_wild:
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
                        hiv = line.split(': ')[1][2:(-2)]
                hextra = "Weather: {hweather}".format(hweather=hweather)
                if hiv:
                    hextra += " / IV: {hiv}".format(hiv=hiv)
                huntr = '!wild {0} {1}|{2}|{3}'.format(hpokeid, huntrgps, hexpire, hextra)
                await utils.safe_delete(message)
                await self.huntr_wild(ctx, hpokeid, huntrgps, hexpire, hextra, reporter="huntr")
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
            raid_details = pokehuntr_dict[message.id]['gym']
            reacttime = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])
            timediff = relativedelta(reacttime, reporttime)
            raidexp = int(reporttime.minute) - int(timediff.minutes)
            if reporttype == "egg":
                egg_level = pokehuntr_dict[message.id]['level']
                raid_channel = await self.huntr_raidegg(ctx, egg_level, raid_details, raidexp, gymhuntrgps)
            elif reporttype == "raid":
                entered_raid = pokehuntr_dict[message.id]['pokemon']
                gymhuntrmoves = pokehuntr_dict[message.id]['moves']
                raid_channel = await self.huntr_raid(ctx, entered_raid, raid_details, raidexp, gymhuntrgps, gymhuntrmoves)
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
                raid_details = painfo[1]
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
                raid_details = painfo[1]
                timeout = int(raidexp)*60
                expiremsg = _('**This {pokemon} raid has expired!**').format(pokemon=entered_raid.title())
            elif "!wild" in message.content.lower():
                if not self.bot.guild_dict[message.guild.id]['configure_dict']['scanners'].get('autowild', False):
                    return
                wild_cog = self.bot.cogs.get('Wild')
                if not wild_cog:
                    logger.error("Wild Cog not loaded")
                    return
                painfo = message.content.replace("!wild", "").strip().split("|")
                reporttype = "wild"
                exptime = painfo[2]
                #minutes = exptime.split()[0][:-1]
                minutes = "45"
                seconds = exptime.split()[1][:-1]
                huntrexp = "{min} min {sec} sec".format(min=minutes, sec=seconds)
                huntrweather = painfo[3]
                entered_wild = painfo[0].lower().strip()
                wild_details = painfo[1]
                location = f"https://www.google.com/maps/search/?api=1&query={wild_details}"
                despawn = (int(minutes) * 60) + int(seconds)
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
            await utils.safe_delete(message)
            if reporttype == "wild":
                await self.huntr_wild(ctx, entered_wild, wild_details, huntrexp, huntrweather)
                return
            elif reporttype == "quest":
                await self.huntr_research(ctx, pokestop, gps, quest, reward)
                return
            else:
                for channelid in self.bot.guild_dict[message.guild.id]['raidchannel_dict']:
                    channel_gps = self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid].get('gymhuntrgps', None)
                    channel_address = self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid].get('address', None)
                    if channel_gps == gps or channel_address == raid_details:
                        channel = self.bot.get_channel(channelid)
                        if embed and channel:
                            await channel.send(embed=embed)
                        if self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid].get('type', None) == 'egg':
                            if not utils.get_level(self.bot, entered_raid):
                                logger.error(f"{entered_raid} not in raid_json")
                                return
                            await raid_cog._eggtoraid(entered_raid, channel, message.author, huntr=moves)
                        elif channel and moves:
                            await channel.send(_("This {entered_raid}'s moves are: **{moves}**").format(entered_raid=entered_raid.title(), moves=moves))
                            try:
                                raid_msg = await channel.get_message(self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid]['raidmessage'])
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
                        pamsg = await message.channel.send(raidmsg, embed=embed)
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
                        pamsg = await message.channel.send(raidmsg, embed=embed)
                self.bot.guild_dict[message.guild.id]['pokealarm_dict'][pamsg.id] = {
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
                    "embed":embed
                }
                await asyncio.sleep(0.25)
                await pamsg.add_reaction(self.bot.config['huntr_report'])
        else:
            await utils.safe_delete(message)
            pokealarm_dict = copy.deepcopy(self.bot.guild_dict[message.guild.id].get('pokealarm_dict', {}))
            alarm_details = pokealarm_dict[message.id]
            embed = alarm_details['embed']
            reporttime = alarm_details['reporttime']
            reporttype = alarm_details['reporttype']
            huntrtime = alarm_details['raidexp']
            reacttime = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])
            timediff = relativedelta(reacttime, reporttime)
            exptime = int(huntrtime) - int(timediff.minutes)
            if reporttype == "egg":
                raid_channel = await self.huntr_raidegg(ctx, alarm_details['level'], alarm_details['gym'], exptime, alarm_details['gps'],  report_user=reactuser)
            elif reporttype == "raid":
                raid_channel = await self.huntr_raid(ctx, alarm_details['pokemon'], alarm_details['gym'], exptime, alarm_details['gps'], alarm_details['moves'], report_user=reactuser)
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
            ctrs_message = await channel.get_message(self.bot.guild_dict[channel.guild.id]['raidchannel_dict'][channel.id]['ctrsmessage'])
        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException, KeyError):
            ctrs_message = None
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
            p_name = pokemon.name.title()
            p_type = utils.get_type(ctx.bot, message.guild, pokemon.id, pokemon.form, pokemon.alolan)
            boss_list.append((((p_name + ' (') + str(pokemon.id)) + ') ') + ''.join(p_type))
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
        raid_embed.add_field(name=_('**Details:**'), value=_('{pokemon} ({pokemonnumber}) {type}').format(pokemon=pokemon.name.title(), pokemonnumber=pokemon.id, type=''.join(utils.get_type(ctx.bot, message.guild, pokemon.id, pokemon.form, pokemon.alolan)), inline=True))
        raid_embed.add_field(name=_('**Weaknesses:**'), value=_('{weakness_list}').format(weakness_list=utils.weakness_to_str(ctx.bot, message.guild, utils.get_weaknesses(ctx.bot, pokemon.name.lower(), pokemon.form, pokemon.alolan))), inline=True)
        raid_embed.add_field(name=_('**Next Group:**'), value=_('Set with **!starttime**'), inline=True)
        raid_embed.add_field(name=_('**Expires:**'), value=_('Set with **!timerset**'), inline=True)
        if gymhuntrmoves:
            raid_embed.add_field(name=_("**Moveset:**"), value=gymhuntrmoves)
        raid_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=message.author.display_name, timestamp=timestamp), icon_url=message.author.avatar_url_as(format=None, static_format='jpg', size=32))
        raid_embed.set_thumbnail(url=pokemon.img_url)
        return raid_embed

    """Reporting"""

    async def huntr_wild(self, ctx, entered_wild, wild_details, huntrexp, huntrweather, reporter=None, report_user=None):
        if report_user:
            ctx.message.author = report_user
        message = ctx.message
        timestamp = (message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])).strftime(_('%I:%M %p (%H:%M)'))
        huntrexpstamp = (message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'], minutes=int(huntrexp.split()[0]), seconds=int(huntrexp.split()[2]))).strftime('%I:%M %p')
        pokemon = pkmn_class.Pokemon.get_pokemon(ctx.bot, entered_wild)
        nearest_stop = ""
        if pokemon:
            entered_wild = pokemon.name.lower()
            pokemon.shiny = False
        else:
            return
        if pokemon.id in ctx.bot.guild_dict[message.channel.guild.id]['configure_dict']['scanners'].setdefault('wildfilter', []):
            return
        wild_types = copy.deepcopy(pokemon.types)
        wild_types.append('None')
        wild_number = pokemon.id
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
        wild_embed = discord.Embed(title=_('Meowth! Click here for exact directions to the wild {pokemon}!').format(pokemon=entered_wild.title()), url=wild_gmaps_link, colour=message.guild.me.colour)
        wild_embed.add_field(name=_('**Details:**'), value=_('{pokemon} ({pokemonnumber}) {type}').format(pokemon=entered_wild.title(), pokemonnumber=str(wild_number), type=''.join(utils.get_type(ctx.bot, message.guild, pokemon.id, pokemon.form, pokemon.alolan))), inline=True)
        wild_embed.add_field(name='**Despawns in:**', value=_('{huntrexp} mins ({huntrexpstamp})').format(huntrexp=huntrexp.split()[0], huntrexpstamp=huntrexpstamp), inline=True)
        if reporter == "huntr":
            wild_embed.add_field(name=huntrweather, value=_('Perform a scan to help find more by clicking [here]({huntrurl}).').format(huntrurl=wild_details), inline=False)
        wild_embed.set_thumbnail(url=pokemon.img_url)
        wild_embed.add_field(name='**Reactions:**', value=_("{emoji}: I'm on my way!").format(emoji=ctx.bot.config['wild_omw']), inline=True)
        wild_embed.add_field(name='\u200b', value=_("{emoji}: The Pokemon despawned!").format(emoji=ctx.bot.config['wild_despawn']), inline=True)
        wild_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=message.author.display_name, timestamp=timestamp), icon_url=message.author.avatar_url_as(format=None, static_format='jpg', size=32))
        despawn = (int(huntrexp.split(' ')[0]) * 60) + int(huntrexp.split(' ')[2])
        if nearest_stop:
            wildreportmsg = await message.channel.send(content=_('Meowth! Wild {pokemon} reported by {member}! Nearest Pokestop: {nearest_stop} | Coordinates: {location_details}').format(pokemon=str(pokemon).title(), member=message.author.mention, nearest_stop=nearest_stop, location_details=wild_coordinates), embed=wild_embed)
        else:
            wildreportmsg = await message.channel.send(content=_('Meowth! Wild {pokemon} reported by {member}! Coordinates: {location_details}').format(pokemon=str(pokemon).title(), member=message.author.mention, location_details=wild_coordinates), embed=wild_embed)
        dm_dict = {}
        for trainer in ctx.bot.guild_dict[message.guild.id].get('trainers', {}):
            if not checks.dm_check(ctx, trainer):
                continue
            user_wants = ctx.bot.guild_dict[message.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('wants', [])
            user_stops = ctx.bot.guild_dict[message.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('stops', [])
            user_types = ctx.bot.guild_dict[message.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('types', [])
            if wild_number in user_wants or nearest_stop.lower() in user_stops or wild_types[0] in user_types or wild_types[1] in user_types:
                try:
                    user = message.guild.get_member(trainer)
                    wild_embed.remove_field(2)
                    wild_embed.remove_field(2)
                    if nearest_stop:
                        wilddmmsg = await user.send(content=_('Meowth! Wild {pokemon} reported by {member} in {channel}! Nearest Pokestop: {nearest_stop} | Coordinates: {location_details}').format(pokemon=str(pokemon).title(), member=message.author.display_name, nearest_stop=nearest_stop, channel=message.channel.mention, location_details=wild_coordinates), embed=wild_embed)
                    else:
                        wilddmmsg = await user.send(content=_('Meowth! Wild {pokemon} reported by {member} in {channel}! Details: {location_details}').format(pokemon=str(pokemon).title(), member=message.author.display_name, channel=message.channel.mention, location_details=wild_details), embed=wild_embed)
                    dm_dict[user.id] = wilddmmsg.id
                except:
                    continue
        await asyncio.sleep(0.25)
        await wildreportmsg.add_reaction(ctx.bot.config['wild_omw'])
        await asyncio.sleep(0.25)
        await wildreportmsg.add_reaction(ctx.bot.config['wild_despawn'])
        await asyncio.sleep(0.25)
        ctx.bot.guild_dict[message.guild.id]['wildreport_dict'][wildreportmsg.id] = {
            'exp':time.time() + despawn,
            'expedit': {"content":wildreportmsg.content, "embedcontent":expiremsg},
            'reportmessage':message.id,
            'reportchannel':message.channel.id,
            'reportauthor':message.author.id,
            'dm_dict':dm_dict,
            'location':wild_details,
            'url':wild_gmaps_link,
            'pokemon':entered_wild,
            'pkmn_obj':str(pokemon),
            'omw':[]
        }

    async def huntr_raid(self, ctx, entered_raid, raid_details, raidexp, gymhuntrgps, gymhuntrmoves, reporter=None, report_user=None):
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
        raid_embed = await self.make_raid_embed(ctx, entered_raid, raid_details, raidexp, gymhuntrgps, gymhuntrmoves)
        raid_channel_name = entered_raid + "-" + utils.sanitize_channel_name(raid_details) + "-bot"
        raid_channel_category = utils.get_category(self.bot, message.channel, utils.get_level(self.bot, entered_raid), category_type="raid")
        raid_channel = await message.guild.create_text_channel(raid_channel_name, overwrites=dict(message.channel.overwrites), category=raid_channel_category)
        await asyncio.sleep(1)
        raidreport = await message.channel.send(content=_('Meowth! {pokemon} raid reported by {member}! Details: {location_details}. Coordinate in {raid_channel}').format(pokemon=str(pokemon).title(), member=message.author.mention, location_details=raid_details, raid_channel=raid_channel.mention), embed=raid_embed)
        ow = raid_channel.overwrites_for(raid_channel.guild.default_role)
        ow.send_messages = True
        try:
            await raid_channel.set_permissions(raid_channel.guild.default_role, overwrite = ow)
        except (discord.errors.Forbidden, discord.errors.HTTPException, discord.errors.InvalidArgument):
            pass
        for role in raid_channel.guild.roles:
            if role.permissions.manage_guild or role.permissions.manage_channels or role.permissions.manage_messages:
                ow = raid_channel.overwrites_for(role)
                ow.manage_channels = True
                ow.manage_messages = True
                ow.manage_roles = True
                try:
                    await raid_channel.set_permissions(role, overwrite = ow)
                except (discord.errors.Forbidden, discord.errors.HTTPException, discord.errors.InvalidArgument):
                    pass
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
            'raidreport': raidreport.id,
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
        dm_dict = {}
        raid_embed.remove_field(2)
        raid_embed.remove_field(2)
        for trainer in ctx.bot.guild_dict[message.guild.id].get('trainers', {}):
            if not checks.dm_check(ctx, trainer):
                continue
            user_gyms = ctx.bot.guild_dict[message.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('gyms', [])
            if raid_details.lower() in user_gyms:
                try:
                    user = message.guild.get_member(trainer)
                    raiddmmsg = await user.send(content=_('Meowth! {pokemon} raid reported by {member}! Details: {location_details}. Coordinate in {raid_channel}').format(pokemon=str(pokemon).title(), member=message.author.mention, location_details=raid_details, raid_channel=raid_channel.mention), embed=raid_embed)
                    dm_dict[user.id] = raiddmmsg.id
                except:
                    continue
        ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid_channel.id]['dm_dict'] = dm_dict
        if report_user:
            raid_reports = self.bot.guild_dict[message.guild.id].setdefault('trainers', {}).setdefault(report_user.id, {}).setdefault('raid_reports', 0) + 1
            self.bot.guild_dict[message.guild.id]['trainers'][report_user.id]['raid_reports'] = raid_reports
        await self.auto_counters(raid_channel, gymhuntrmoves)
        return raid_channel

    async def huntr_raidegg(self, ctx, egg_level, raid_details, raidexp, gymhuntrgps, reporter=None, report_user=None):
        raid_cog = self.bot.cogs.get('Raid')
        if report_user:
            ctx.message.author = report_user
        message = ctx.message
        timestamp = (message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])).strftime(_('%I:%M %p (%H:%M)'))
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])
        weather = ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'].get(message.channel.id, {}).get('weather', None)
        raid_embed = await self.make_egg_embed(ctx, egg_level, raid_details, raidexp, gymhuntrgps, reporter)
        raid_channel_name = _('level-{egg_level}-egg-').format(egg_level=egg_level)
        raid_channel_name += utils.sanitize_channel_name(raid_details) + "-bot"
        raid_channel_category = utils.get_category(self.bot, message.channel, egg_level, category_type="raid")
        raid_channel = await message.guild.create_text_channel(raid_channel_name, overwrites=dict(message.channel.overwrites), category=raid_channel_category)
        await asyncio.sleep(1)
        raidreport = await message.channel.send(content=_('Meowth! Level {level} raid egg reported by {member}! Details: {location_details}. Coordinate in {raid_channel}').format(level=egg_level, member=message.author.mention, location_details=raid_details, raid_channel=raid_channel.mention), embed=raid_embed)
        ow = raid_channel.overwrites_for(raid_channel.guild.default_role)
        ow.send_messages = True
        try:
            await raid_channel.set_permissions(raid_channel.guild.default_role, overwrite = ow)
        except (discord.errors.Forbidden, discord.errors.HTTPException, discord.errors.InvalidArgument):
            pass
        for role in raid_channel.guild.roles:
            if role.permissions.manage_guild or role.permissions.manage_channels or role.permissions.manage_messages:
                ow = raid_channel.overwrites_for(role)
                ow.manage_channels = True
                ow.manage_messages = True
                ow.manage_roles = True
                try:
                    await raid_channel.set_permissions(role, overwrite = ow)
                except (discord.errors.Forbidden, discord.errors.HTTPException, discord.errors.InvalidArgument):
                    pass
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
            'raidreport': raidreport.id,
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
        dm_dict = {}
        raid_embed.remove_field(2)
        raid_embed.remove_field(2)
        for trainer in ctx.bot.guild_dict[message.guild.id].get('trainers', {}):
            if not checks.dm_check(ctx, trainer):
                continue
            user_gyms = ctx.bot.guild_dict[message.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('gyms', [])
            if raid_details.lower() in user_gyms:
                try:
                    user = message.guild.get_member(trainer)
                    raiddmmsg = await user.send(content=_('Meowth! Level {level} raid egg reported by {member}! Details: {location_details}. Coordinate in {raid_channel}').format(level=egg_level, member=message.author.mention, location_details=raid_details, raid_channel=raid_channel.mention), embed=raid_embed)
                    dm_dict[user.id] = raiddmmsg.id
                except:
                    continue
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
        research_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/field-research.png?cache=1')
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
            reward = f"{string.capwords(reward, ' ')} {''.join(utils.get_type(self.bot, guild, pokemon.id, pokemon.form, pokemon.alolan))}"
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
        description = "**Marilla Park.**\nMewtwo\n**CP:** 60540 - **Moves:** Confusion / Shadow Ball\n*Raid Ending: 0 hours 46 min 50 sec*"
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

def setup(bot):
    bot.add_cog(Huntr(bot))
