import asyncio
import copy
import re
import time
import datetime
from dateutil.relativedelta import relativedelta
import dateparser
import urllib

import discord
from discord.ext import commands

import meowth
from meowth import utils, checks

class Huntr:
    def __init__(self, bot):
        self.bot = bot
        self.event_loop = asyncio.get_event_loop()

    """Handlers"""

    async def on_message(self, message):
        ctx = await self.bot.get_context(message)
        if not ctx.guild:
            return
        if message.guild and message.webhook_id and ("!raid" in message.content or "!raidegg" in message.content or "!wild" in message.content):
            await self.on_pokealarm(ctx)
        if (str(message.author) == 'GymHuntrBot#7279') or (str(message.author) == 'HuntrBot#1845'):
            await self.on_huntr(ctx)

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
        pokealarm_dict = copy.deepcopy(ctx.bot.guild_dict[channel.guild.id].get('pokealarm_dict',{}))
        pokehuntr_dict = copy.deepcopy(ctx.bot.guild_dict[channel.guild.id].get('pokehuntr_dict',{}))
        if message.id in pokealarm_dict.keys() and not user.bot and str(payload.emoji) == "✅":
            await on_pokealarm(ctx, user)
        if message.id in pokehuntr_dict.keys() and not user.bot and str(payload.emoji) == "✅":
            await self.on_huntr(ctx, user)

    async def on_huntr(self, ctx, reactuser=None):
        message = ctx.message
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])).strftime('%I:%M %p')
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])
        pokehuntr_dict = copy.deepcopy(self.bot.guild_dict[message.guild.id].get('pokehuntr_dict',{}))
        if not reactuser:
            if message.embeds and (message.author.id == 329412230481444886 or message.author.id == 295116861920772098 or message.author.id == message.guild.me.id):
                huntrgps = ""
                try:
                    huntrgps = message.embeds[0].url.split('#')[1]
                except IndexError:
                    req = urllib.request.Request(message.embeds[0].url, headers={
                        'User-Agent': 'Magic Browser',
                    })
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
            if (message.author.id == 329412230481444886 or message.author.id == message.guild.me.id) and message.embeds:
                if (len(message.embeds[0].title.split(' ')) == 5) and self.bot.guild_dict[message.guild.id]['configure_dict']['scanners']['autoraid']:
                    match = re.search('[* ]*([a-zA-Z ]*)[* .]*\n(.*)\n[* CP:]*([0-9]*)[ \-*Moves:]*(.*)\n[*a-zA-Z: ]*([0-2])[ a-z]*([0-9]*)[ a-z]*([0-9]*)', message.embeds[0].description)
                    raid_details = match.group(1)
                    pokemon = match.group(2).lower()
                    moveset = match.group(4)
                    raidexp = match.group(6)
                    await message.delete()
                    for channelid in self.bot.guild_dict[message.guild.id]['raidchannel_dict']:
                        try:
                            if self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid].get('gymhuntrgps', False) == huntrgps:
                                channel = self.bot.get_channel(channelid)
                                if self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid]['type'] == 'egg':
                                    await self.bot.eggtoraid(ghpokeid.lower().strip(), channel, author=message.author, huntr=moveset)
                                raidmsg = await channel.get_message(self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid]['raidmessage'])
                                if raidmsg.embeds[0].fields[2].name != moveset:
                                    await channel.send(_("This {pokemon}'s moves are: **{moves}**").format(pokemon=pokemon.title(), moves=moveset))
                        except KeyError:
                            pass
                    auto_report = True if int(utils.get_level(self.bot, pokemon)) in self.bot.guild_dict[message.guild.id]['configure_dict']['scanners']['raidlvls'] else False
                    await self.huntr_raid(ctx, pokemon, raid_details, raidexp, huntrgps, moveset, auto_report)
                    return
                elif (len(message.embeds[0].title.split(' ')) == 6) and self.bot.guild_dict[message.guild.id]['configure_dict']['scanners']['autoegg']:
                    await message.channel.send(f"`{message.embeds[0].description}`")
                    match = re.search('[* ]*([a-zA-Z ]*)[* .]*\n[*:a-zA-Z ]*([0-2]*)[ a-z]*([0-9]*)[ a-z]*([0-9]*)', message.embeds[0].description)
                    egg_level = message.embeds[0].title.split(' ')[1]
                    raid_details = match.group(1)
                    raidexp = match.group(3)
                    await message.delete()
                    for channelid in self.bot.guild_dict[message.guild.id]['raidchannel_dict']:
                        try:
                            if self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid].get('gymhuntrgps', False) == huntrgps:
                                break
                        except KeyError:
                            pass
                    auto_report = True if int(ghegglevel) in self.bot.guild_dict[message.guild.id]['configure_dict']['scanners']['egglvls'] else False
                    await self.huntr_raidegg(ctx, egg_level, raid_details, raidexp, huntrgps, auto_report)
                    return
            if (message.author.id == 295116861920772098) and message.embeds and self.bot.guild_dict[message.guild.id]['configure_dict']['scanners']['autowild']:
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
                await message.delete()
                await self.huntr_wild(ctx, hpokeid, huntrgps, hexpire, hextra)
                return
        else:
            await message.delete()
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

    async def on_pokealarm(self, message, reactuser=None):
        """Requires a specific message.content format, which is "content" in PokeAlarm
        Raid format = !raid <mon_name> <gym_name> <raid_time_left>|<lat>,<lng>|<quick_move> / <charge_move>
        Raidegg format = !raidegg <egg_lvl> <gym_name> <hatch_time_left>|<lat>,<lng>
        Wild format = !wild <mon_name> <lat>,<lng>|<time_left>|Weather: <weather> / IV: <iv>
        I also recommend to set the username to just PokeAlarm"""
        pokealarm_dict = copy.deepcopy(self.bot.guild_dict[message.guild.id].get('pokealarm_dict',{}))
        return


        if not reactuser:
            reporttype = None
            report = None
            embed = message.embeds[0] if message.embeds else None
            await message.delete()
            now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])
            painfo = message.content.split("|")
            if "!raidegg" in message.content.lower():
                reporttype = "egg"
                gps = painfo.pop(1)
                painfo = " ".join(painfo).split()[1:-1]
                level = painfo.pop(0)
                pokeid = None
                time = painfo.pop(-1)[:-1]
                gym = " ".join(painfo)
                timeout = int(time)*60
                expiremsg = _('**This level {level} raid egg has hatched!**').format(level=pokealarm_dict[alertid]['level'])
                huntr = "!raidegg {level} {gym} {time}|{gps}".format(level=level,gym=gym,time=time,gps=gps)
            elif "!raid" in message.content.lower():
                reporttype = "raid"
                gps = painfo.pop(1)
                moves = painfo.pop(1)
                painfo = " ".join(painfo).split()[1:-1]
                pokeid = painfo.pop(0)
                level = 0
                time = painfo.pop(-1)[:-1]
                gym = " ".join(painfo)
                timeout = int(time)*60
                expiremsg = _('**This {pokemon} raid has expired!**').format(pokemon=pokeid.title())
                huntr = "!raid {pokeid} {gym} {time}|{gps}|{moves}".format(pokeid=pokeid,gym=gym,time=time,gps=gps,moves=moves)
            elif "!wild" in message.content.lower():
                reporttype = "wild"
                time = painfo.pop(1).split()
                minutes = time.pop(0)[:-1]
                seconds = time.pop(0)[:-1]
                time = "{min} min {sec} sec".format(min=minutes,sec=seconds)
                weather = painfo.pop(1)
                painfo = " ".join(painfo).split()[1:]
                pokeid = painfo.pop(0)
                location = " ".join(painfo)
                location = "https://www.google.com/maps/dir/Current+Location/{location}".format(location=location)
                despawn = (int(minutes) * 60) + int(seconds)
                huntr = '!wild {pokeid} {gps}|{time}|{weather}'.format(pokeid=pokeid,gps=location,time=time,weather=weather)
            if reporttype == "wild":
                await _wild(message, content="",huntr=huntr)
                return
            else:
                for channelid in self.bot.guild_dict[message.guild.id]['raidchannel_dict']:
                    if self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid].get('gymhuntrgps',None) == gps:
                        channel = self.bot.get_channel(channelid)
                        if self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid].get('type',None) == 'egg':
                            await self.bot.eggtoraid(pokeid.lower().strip(), channel, message.author, message.content)
                        if embed and channel:
                            await channel.send(embed=embed)
                        return
                if self.bot.guild_dict[message.guild.id]['configure_dict']['scanners'].get('alarmaction',None) == 'auto':
                    if reporttype == "egg":
                        huntr = "!raidegg {level} {gym} {time}|{gps}".format(level=level,gym=gym,time=time,gps=gps)
                        raid_channel = await _raidegg(message, content="",huntr=huntr)
                    elif reporttype == "raid":
                        huntr = "!raid {pokeid} {gym} {time}|{gps}|{moves}".format(pokeid=pokeid,gym=gym,time=time,gps=gps,moves=moves)
                        raid_channel = await _raid(message, content="",huntr=huntr)
                    if embed and raid_channel:
                        await raid_channel.send(embed=embed)
                elif self.bot.guild_dict[message.guild.id]['configure_dict']['scanners'].get('alarmaction',None) == 'react':
                    if reporttype == "egg":
                        pamsg = await message.channel.send(("If you want me to report this level {level} egg, just react!").format(level=level),embed=embed)
                    elif reporttype == "raid":
                        pamsg = await message.channel.send(("If you want me to report this {pokeid} raid, just react!").format(pokeid=pokeid),embed=embed)
                    await asyncio.sleep(0.25)
                    await pamsg.add_reaction('✅')
                    pokealarm_dict[pamsg.id] = {
                        "exp":time.time() + timeout,
                        'expedit': {"content":None,"embedcontent":expiremsg},
                        "reporttype":reporttype,
                        "reportchannel":message.channel.id,
                        "level":level,
                        "pokemon":pokeid,
                        "reporttime":now,
                        "huntr":huntr,
                        "embed":embed
                    }
                    self.bot.guild_dict[message.guild.id]['pokealarm_dict'] = pokealarm_dict
        else:
            huntr = pokealarm_dict[message.id]['huntr']
            embed = pokealarm_dict[message.id]['embed']
            reporttime = pokealarm_dict[message.id]['reporttime']
            reporttype = pokealarm_dict[message.id]['reporttype']
            huntrtime = huntr.split("|")[0][-1]
            reacttime = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])
            timediff = relativedelta(reacttime, reporttime)
            time = int(huntrtime) - int(timediff.minutes)
            huntr = huntr.replace(huntrtime,time)
            if reporttype == "egg":
                raid_channel = await _raidegg(message, content="",huntr=huntr)
            elif reporttype == "raid":
                raid_channel = await _raid(message, content="",huntr=huntr)
            if embed and raid_channel:
                await raid_channel.send(embed=embed)
            await message.delete()


    """Reporting"""

    async def huntr_wild(self, ctx, entered_wild, wild_details, huntrexp, huntrweather):
        message = ctx.message
        timestamp = (message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])).strftime(_('%I:%M %p (%H:%M)'))
        huntrexpstamp = (message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'], minutes=int(huntrexp.split()[0]), seconds=int(huntrexp.split()[2]))).strftime('%I:%M %p')
        wild_number = ctx.bot.pkmn_list.index(entered_wild) + 1
        wild_img_url = 'https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/pkmn_icons/pokemon_icon_{0}_00.png?cache=1'.format(str(wild_number).zfill(3))
        expiremsg = _('**This {pokemon} has despawned!**').format(pokemon=entered_wild.title())
        wild_gmaps_link = 'https://www.google.com/maps/dir/Current+Location/{0}'.format(wild_details.split("#")[1])
        wild_embed = discord.Embed(title=_('Meowth! Click here for exact directions to the wild {pokemon}!').format(pokemon=entered_wild.title()), url=wild_gmaps_link, colour=message.guild.me.colour)
        wild_embed.add_field(name='**Details:**', value=_('{pokemon} ({pokemonnumber}) {type}').format(pokemon=entered_wild.title(), pokemonnumber=str(wild_number), type=''.join(utils.get_type(ctx.bot, message.guild, wild_number)), inline=True))
        wild_embed.add_field(name='**Despawns in:**', value=_('{huntrexp} mins ({huntrexpstamp})').format(huntrexp=huntrexp.split()[0], huntrexpstamp=huntrexpstamp), inline=True)
        wild_embed.add_field(name=huntrweather, value=_('Perform a scan to help find more by clicking [here]({huntrurl}).').format(huntrurl=wild_details), inline=False)
        wild_embed.set_thumbnail(url=wild_img_url)
        wild_embed.add_field(name='**Reactions:**', value=_("🏎: I'm on my way!"))
        wild_embed.add_field(name='\u200b', value=_("💨: The Pokemon despawned!"))
        wild_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=message.author.display_name, timestamp=timestamp), icon_url=message.author.avatar_url_as(format=None, static_format='jpg', size=32))
        despawn = (int(huntrexp.split(' ')[0]) * 60) + int(huntrexp.split(' ')[2])
        wildreportmsg = await message.channel.send(content=_('Meowth! Wild {pokemon} reported by {member}! Details: {location_details}').format(pokemon=entered_wild.title(), member=message.author.mention, location_details=wild_details), embed=wild_embed)
        dm_dict = {}
        for trainer in ctx.bot.guild_dict[message.guild.id].get('trainers', {}):
            user = message.guild.get_member(trainer)
            if not user:
                continue
            perms = user.permissions_in(message.channel)
            if not perms.read_messages:
                continue
            if wild_number in ctx.bot.guild_dict[message.guild.id].get('trainers', {})[trainer].setdefault('wants', []):
                wilddmmsg = await user.send(content=_('Meowth! Wild {pokemon} reported by {member} in {channel}! Details: {location_details}').format(pokemon=entered_wild.title(), member=message.author.display_name, channel=message.channel.mention, location_details=wild_details), embed=wild_embed)
                dm_dict[user.id] = wilddmmsg.id
        await asyncio.sleep(0.25)
        await wildreportmsg.add_reaction('🏎')
        await asyncio.sleep(0.25)
        await wildreportmsg.add_reaction('💨')
        await asyncio.sleep(0.25)
        wild_dict = copy.deepcopy(ctx.bot.guild_dict[message.guild.id].get('wildreport_dict',{}))
        wild_dict[wildreportmsg.id] = {
            'exp':time.time() + despawn,
            'expedit': {"content":wildreportmsg.content,"embedcontent":expiremsg},
            'reportmessage':message.id,
            'reportchannel':message.channel.id,
            'reportauthor':message.author.id,
            'dm_dict':dm_dict,
            'location':wild_details,
            'url':wild_gmaps_link,
            'pokemon':entered_wild,
            'omw':[]
        }

    async def huntr_raid(self, ctx, entered_raid, raid_details, raidexp, gymhuntrgps, gymhuntrmoves, auto_report = True):
        message = ctx.message
        timestamp = (message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])).strftime(_('%I:%M %p (%H:%M)'))
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])
        rgx = '[^a-zA-Z0-9]'
        pkmn_match = next((p for p in ctx.bot.pkmn_list if re.sub(rgx, '', p) == re.sub(rgx, '', entered_raid)), None)
        raid_match = True if entered_raid in utils.get_raidlist(self.bot) else False
        if (not raid_match):
            await message.channel.send(_('Meowth! The Pokemon {pokemon} does not appear in raids!').format(pokemon=entered_raid.capitalize()))
            return
        elif utils.get_level(self.bot, entered_raid) == "EX":
            await message.channel.send(_("Meowth! The Pokemon {pokemon} only appears in EX Raids! Use **!exraid** to report one!").format(pokemon=entered_raid.capitalize()))
            return
        weather = ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'].get(message.channel.id,{}).get('weather', None)
        raid_gmaps_link = "https://www.google.com/maps/dir/Current+Location/{0}".format(gymhuntrgps)
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        gym_info = ""
        if gym_matching_cog:
            gym_info, raid_details, gym_url = await gym_matching_cog.get_gym_info(ctx, raid_details, "raid")
            if gym_url:
                raid_gmaps_link = gym_url
        if not raid_details:
            return
        raid = discord.utils.get(message.guild.roles, name=entered_raid)
        if raid == None:
            roletest = ""
        else:
            roletest = _("{pokemon} - ").format(pokemon=raid.mention)
        raid_number = ctx.bot.pkmn_list.index(entered_raid) + 1
        raid_img_url = 'https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/pkmn_icons/pokemon_icon_{0}_00.png?cache=1'.format(str(raid_number).zfill(3))
        raid_embed = discord.Embed(title=_('Meowth! Click here for directions to the raid!'), description=gym_info, url=raid_gmaps_link, colour=message.guild.me.colour)
        raid_embed.add_field(name=_('**Details:**'), value=_('{pokemon} ({pokemonnumber}) {type}').format(pokemon=entered_raid.capitalize(), pokemonnumber=str(raid_number), type=''.join(utils.get_type(self.bot, message.guild, raid_number)), inline=True))
        raid_embed.add_field(name=_('**Weaknesses:**'), value=_('{weakness_list}').format(weakness_list=utils.weakness_to_str(self.bot, message.guild, utils.get_weaknesses(self.bot, entered_raid))), inline=True)
        raid_embed.add_field(name=_('**Next Group:**'), value=_('Set with **!starttime**'), inline=True)
        raid_embed.add_field(name=_('**Expires:**'), value=_('Set with **!timerset**'), inline=True)
        raid_embed.add_field(name=gymhuntrmoves, value=_("Perform a scan to help find more by clicking [here](https://gymhuntr.com/#{huntrurl}).").format(huntrurl=gymhuntrgps), inline=False)
        raid_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=message.author.display_name, timestamp=timestamp), icon_url=message.author.avatar_url_as(format=None, static_format='jpg', size=32))
        raid_embed.set_thumbnail(url=raid_img_url)
        report_embed = raid_embed
        if auto_report:
            raid_channel_name = entered_raid + "-" + utils.sanitize_channel_name(raid_details) + "-bot"
            raid_channel_category = utils.get_category(self.bot, message.channel, utils.get_level(self.bot, entered_raid), category_type="raid")
            raid_channel = await message.guild.create_text_channel(raid_channel_name, overwrites=dict(message.channel.overwrites), category=raid_channel_category)
            await asyncio.sleep(1)
            raidreport = await message.channel.send(content=_('Meowth! {pokemon} raid reported by {member}! Details: {location_details}. Coordinate in {raid_channel}').format(pokemon=entered_raid.capitalize(), member=message.author.mention, location_details=raid_details, raid_channel=raid_channel.mention), embed=report_embed)
            ow = raid_channel.overwrites_for(raid_channel.guild.default_role)
            ow.send_messages = True
            try:
                await raid_channel.set_permissions(raid_channel.guild.default_role, overwrite = ow)
            except (discord.errors.Forbidden, discord.errors.HTTPException, discord.errors.InvalidArgument):
                pass
            for role in raid_channel.guild.role_hierarchy:
                if role.permissions.manage_guild or role.permissions.manage_channels or role.permissions.manage_messages:
                    ow = raid_channel.overwrites_for(role)
                    ow.manage_channels = True
                    ow.manage_messages = True
                    ow.manage_roles = True
                    try:
                        await raid_channel.set_permissions(role, overwrite = ow)
                    except (discord.errors.Forbidden, discord.errors.HTTPException, discord.errors.InvalidArgument):
                        pass
            raidmsg = _("{roletest}Meowth! {pokemon} raid reported by {member} in {citychannel}! Details: {location_details}. Coordinate here!\n\nClick the question mark reaction to get help on the commands that work in here.\n\nThis channel will be deleted five minutes after the timer expires.").format(roletest=roletest, pokemon=entered_raid.title(), member=message.author.mention, citychannel=message.channel.mention, location_details=raid_details)
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
                'egglevel': '0',
                'moveset': 0,
                'weather': weather,
                'gymhuntrgps' : gymhuntrgps
            }
            if raidexp is not False:
                await self.bot.timerset(raid_channel, raidexp)
            else:
                await raid_channel.send(content=_('Meowth! Hey {member}, if you can, set the time left on the raid using **!timerset <minutes>** so others can check it with **!timer**.').format(member=message.author.mention))
            await raid_channel.send("This raid was reported by a bot. If it is a duplicate of a raid already reported by a human, I can delete it with three **!duplicate** messages.")
            if str(level) in ctx.bot.guild_dict[message.guild.id]['configure_dict']['counters']['auto_levels']:
                try:
                    ctrs_dict = await ctx.bot._get_generic_counters(message.guild, entered_raid, weather)
                    ctrsmsg = "Here are the best counters for the raid boss in currently known weather conditions! Update weather with **!weather**. If you know the moveset of the boss, you can react to this message with the matching emoji and I will update the counters."
                    ctrsmessage = await raid_channel.send(content=ctrsmsg,embed=ctrs_dict[0]['embed'])
                    ctrsmessage_id = ctrsmessage.id
                    await ctrsmessage.pin()
                    for moveset in ctrs_dict:
                        await ctrsmessage.add_reaction(ctrs_dict[moveset]['emoji'])
                        await asyncio.sleep(0.25)
                except:
                    ctrs_dict = {}
                    ctrsmessage_id = None
            else:
                ctrs_dict = {}
                ctrsmessage_id = None
            ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid_channel.id]['ctrsmessage'] = ctrsmessage_id
            ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid_channel.id]['ctrs_dict'] = ctrs_dict
            self.event_loop.create_task(self.bot.expiry_check(raid_channel))
            return raid_channel
        else:
            pokehuntr_dict = copy.deepcopy(self.bot.guild_dict[message.guild.id].get('pokehuntr_dict',{}))
            raidreport = await message.channel.send(content=_('{roletest}Meowth! {pokemon} raid reported by {member}! Details: {location_details}. React if you want to make a channel for this raid!').format(roletest=roletest,pokemon=entered_raid.title(), member=message.author.mention, location_details=raid_details), embed=raid_embed)
            await asyncio.sleep(0.25)
            await raidreport.add_reaction('✅')
            pokehuntr_dict[raidreport.id] = {
                "exp":time.time() + (raidexp * 60),
                'expedit': {"content":raidreport.content.split(" React")[0],"embedcontent":_('**This {pokemon} raid has expired!**').format(pokemon=entered_raid)},
                "reporttype":"raid",
                "reportchannel":message.channel.id,
                "level":0,
                "pokemon":entered_raid,
                "reporttime":now,
                "gym":raid_details,
                "gps":gymhuntrgps,
                "moves":gymhuntrmoves,
                "embed":raid_embed
            }
            self.bot.guild_dict[message.guild.id]['pokehuntr_dict'] = pokehuntr_dict
            return

    async def huntr_raidegg(self, ctx, egg_level, raid_details, raidexp, gymhuntrgps, auto_report=True):
        message = ctx.message
        timestamp = (message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])).strftime(_('%I:%M %p (%H:%M)'))
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])
        weather = ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'].get(message.channel.id,{}).get('weather', None)
        raid_gmaps_link = "https://www.google.com/maps/dir/Current+Location/{0}".format(gymhuntrgps)
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
            p_name = utils.get_name(self.bot, p).title()
            p_type = utils.get_type(self.bot, message.guild, p)
            boss_list.append((((p_name + ' (') + str(p)) + ') ') + ''.join(p_type))
        raid_img_url = 'https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/eggs/{}?cache=1'.format(str(egg_img))
        raid_embed = discord.Embed(title=_('Meowth! Click here for directions to the coming raid!'), description=gym_info, url=raid_gmaps_link, colour=message.guild.me.colour)
        if len(egg_info['pokemon']) > 1:
            raid_embed.add_field(name=_('**Possible Bosses:**'), value=_('{bosslist1}').format(bosslist1='\n'.join(boss_list[::2])), inline=True)
            raid_embed.add_field(name='\u200b', value=_('{bosslist2}').format(bosslist2='\n'.join(boss_list[1::2])), inline=True)
        else:
            raid_embed.add_field(name=_('**Possible Bosses:**'), value=_('{bosslist}').format(bosslist=''.join(boss_list)), inline=True)
            raid_embed.add_field(name='\u200b', value='\u200b', inline=True)
        raid_embed.add_field(name=_('**Next Group:**'), value=_('Set with **!starttime**'), inline=True)
        raid_embed.add_field(name=_('**Hatches:**'), value=_('Set with **!timerset**'), inline=True)
        raid_embed.add_field(name="\u200b", value=_("Perform a scan to help find more by clicking [here](https://gymhuntr.com/#{huntrurl}).").format(huntrurl=gymhuntrgps), inline=False)
        raid_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=message.author.display_name, timestamp=timestamp), icon_url=message.author.avatar_url_as(format=None, static_format='jpg', size=32))
        raid_embed.set_thumbnail(url=raid_img_url)
        if auto_report:
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
            for role in raid_channel.guild.role_hierarchy:
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
                await self.bot.timerset(raid_channel, raidexp)
            else:
                await raid_channel.send(content=_('Meowth! Hey {member}, if you can, set the time left until the egg hatches using **!timerset <minutes>** so others can check it with **!timer**.').format(member=message.author.mention))
            await raid_channel.send("This egg was reported by a bot. If it is a duplicate of a raid already reported by a human, I can delete it with three **!duplicate** messages.")
            if len(ctx.bot.raid_info['raid_eggs'][egg_level]['pokemon']) == 1:
                await self.bot.eggassume(ctx, 'assume ' + utils.get_name(self.bot, ctx.bot.raid_info['raid_eggs'][egg_level]['pokemon'][0]), raid_channel)
            elif egg_level == "5" and ctx.bot.guild_dict[raid_channel.guild.id]['configure_dict']['settings'].get('regional',None) in ctx.bot.raid_info['raid_eggs']["5"]['pokemon']:
                await self.bot.eggassume(ctx, 'assume ' + utils.get_name(self.bot, ctx.bot.guild_dict[raid_channel.guild.id]['configure_dict']['settings']['regional']), raid_channel)
            self.event_loop.create_task(self.bot.expiry_check(raid_channel))
        else:
            raidreport = await message.channel.send(content=_('Meowth! Level {level} raid egg reported by {member}! Details: {location_details}. React if you want to make a channel for this raid!').format(level=egg_level, member=message.author.mention, location_details=raid_details), embed=raid_embed)
            await asyncio.sleep(0.25)
            await raidreport.add_reaction('✅')
            pokehuntr_dict = copy.deepcopy(self.bot.guild_dict[message.guild.id].get('pokehuntr_dict',{}))
            pokehuntr_dict[raidreport.id] = {
                "exp":time.time() + (int(raidexp) * 60),
                'expedit': {"content":raidreport.content.split(" React")[0],"embedcontent": _('**This level {level} raid egg has hatched!**').format(level=egg_level)},
                "reporttype":"egg",
                "reportchannel":message.channel.id,
                "level":egg_level,
                "pokemon":None,
                "reporttime":now,
                "gym":raid_details,
                "gps":gymhuntrgps,
                "embed":raid_embed
            }
            self.bot.guild_dict[message.guild.id]['pokehuntr_dict'] = pokehuntr_dict
            return

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def huntrraid(self, ctx):
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        await message.delete()
        description = "**Marilla Park.**\nMewtwo\n**CP:** 60540 - **Moves:** Confusion / Shadow Ball\n*Raid Ending: 0 hours 46 min 50 sec*"
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
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        await message.delete()
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
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        await message.delete()
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
