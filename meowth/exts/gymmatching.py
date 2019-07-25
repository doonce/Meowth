import asyncio
import copy
import re
import time
import datetime
import dateparser
import textwrap
import logging
import aiohttp
import os
import json
import functools
from dateutil.relativedelta import relativedelta

import discord
from discord.ext import commands, tasks

from meowth import checks, errors
from meowth.exts import pokemon as pkmn_class
from meowth.exts import utilities as utils

class GymMatching(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.gym_data = self.init_json()
        self.stop_data = self.init_stop_json()

    def init_json(self):
        try:
            with open(os.path.join('data', 'gym_data.json')) as fd:
                return json.load(fd)
        except:
            return {}

    def init_stop_json(self):
        try:
            with open(os.path.join('data', 'stop_data.json')) as fd:
                return json.load(fd)
        except:
            return {}

    def get_gyms(self, guild_id):
        return self.gym_data.get(str(guild_id), {})

    def get_stops(self, guild_id):
        return self.stop_data.get(str(guild_id), {})

    def poi_match(self, poi_name, gyms=None, stops=None):
        if not stops and not gyms:
            return (None, None)
        if not stops:
            stops = {}
        if not gyms:
            gyms = {}
        pois = {**gyms, **stops}
        match, score = utils.get_match(list(pois.keys()), poi_name)
        if match:
            match = pois[match].get('alias', match)
        return(match, score)

    async def find_nearest_stop(self, coord, guild_id):
        stops = self.get_stops(guild_id)
        if not stops:
            return None
        stop_search = {k: (float(stops[k]["coordinates"].split(",")[0]), float(stops[k]["coordinates"].split(",")[1])) for k,v in stops.items()}
        dist = lambda s, key: (float(s[0]) - float(stop_search[key][0])) ** 2 + \
                              (float(s[1]) - float(stop_search[key][1])) ** 2
        nearest_stop = min(stop_search, key=functools.partial(dist, coord))
        return stops[nearest_stop].get('alias', nearest_stop)

    async def find_nearest_gym(self, coord, guild_id):
        gyms = self.get_gyms(guild_id)
        if not gyms:
            return None
        gym_search = {k: (float(gyms[k]["coordinates"].split(",")[0]), float(gyms[k]["coordinates"].split(",")[1])) for k,v in gyms.items()}
        dist = lambda s, key: (float(s[0]) - float(gym_search[key][0])) ** 2 + \
                              (float(s[1]) - float(gym_search[key][1])) ** 2
        nearest_gym = min(gym_search, key=functools.partial(dist, coord))
        return gyms[nearest_gym].get('alias', nearest_gym)

    async def find_nearest_poi(self, coord, guild_id):
        gyms = self.get_gyms(guild_id)
        stops = self.get_stops(guild_id)
        if not gyms and not stops:
            return None
        pois = {**gyms, **stops}
        poi_search = {k: (float(pois[k]["coordinates"].split(",")[0]), float(pois[k]["coordinates"].split(",")[1])) for k,v in pois.items()}
        dist = lambda s, key: (float(s[0]) - float(poi_search[key][0])) ** 2 + \
                              (float(s[1]) - float(poi_search[key][1])) ** 2
        nearest_poi = min(poi_search, key=functools.partial(dist, coord))
        return pois[nearest_poi].get('alias', nearest_poi)

    def do_gym_stats(self, guild_id, channel_dict):
        trainers = 0
        address = channel_dict.get('address', None)
        gyms = self.get_gyms(guild_id)
        if address in gyms:
            egg_level = channel_dict.get('egg_level', 0)
            pokemon = channel_dict.get('pokemon', "")
            boss = channel_dict.get('pkmn_obj', "Egg")
            if egg_level == "0":
                egg_level = utils.get_level(self.bot, pokemon)
            if channel_dict.get('battling', []):
                for lobby in channel_dict.get('battling', []):
                    for trainer in lobby['starting_dict']:
                        trainers += lobby['starting_dict'][trainer]['count']
            if channel_dict.get('completed', []):
                for lobby in channel_dict.get('completed', []):
                    for trainer in lobby['starting_dict']:
                        trainers += lobby['starting_dict'][trainer]['count']
            if channel_dict.get('lobby', False):
                for trainer in channel_dict['lobby']['starting_dict']:
                    trainers += channel_dict['lobby']['starting_dict'][trainer]['count']
            try:
                with open(os.path.join('data', 'gym_stats.json'), 'r') as fd:
                    data = json.load(fd)
            except:
                    data = {}
            test_var = data.setdefault(str(guild_id), {}).setdefault(address, {"total_raids":0, "completed_raids":0, "completed_trainers":0}).setdefault(egg_level, {"total_raids":0, "completed_raids":0, "completed_trainers":0}).setdefault(boss, {"total_raids":0, "completed_raids":0, "completed_trainers":0})
            gym_total = data[str(guild_id)][address]['total_raids'] + 1
            level_total = data[str(guild_id)][address][egg_level]['total_raids'] + 1
            boss_total = data[str(guild_id)][address][egg_level][boss]['total_raids'] + 1
            gym_trainers = data[str(guild_id)][address]['completed_trainers'] + trainers
            level_trainers = data[str(guild_id)][address][egg_level]['completed_trainers'] + trainers
            boss_trainers = data[str(guild_id)][address][egg_level][boss]['completed_trainers'] + trainers
            if trainers:
                gym_complete = data[str(guild_id)][address]['completed_raids'] + 1
                level_complete = data[str(guild_id)][address][egg_level]['completed_raids'] + 1
                boss_complete = data[str(guild_id)][address][egg_level][boss]['completed_raids'] + 1
                data[str(guild_id)][address]['completed_raids'] = gym_complete
                data[str(guild_id)][address][egg_level]['completed_raids'] = level_complete
                data[str(guild_id)][address][egg_level][boss]['completed_raids'] = boss_complete
            data[str(guild_id)][address]['total_raids'] = gym_total
            data[str(guild_id)][address][egg_level]['total_raids'] = level_total
            data[str(guild_id)][address][egg_level][boss]['total_raids'] = boss_total
            data[str(guild_id)][address]['completed_trainers'] = gym_trainers
            data[str(guild_id)][address][egg_level]['completed_trainers'] = level_trainers
            data[str(guild_id)][address][egg_level][boss]['completed_trainers'] = boss_trainers
            with open(os.path.join('data', 'gym_stats.json'), 'w') as fd:
                json.dump(data, fd, indent=2, separators=(', ', ': '))

    @commands.command()
    @checks.is_manager()
    async def poi_json(self, ctx, target=None, action=None):
        """Edits stop_info.json and gym_info.json

        Usage: !poi_json [gym/stop] [add/remove]"""
        message = ctx.message
        channel = message.channel
        author = message.author
        guild = message.guild
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[guild.id]['configure_dict']['settings']['offset']))
        error = False
        first = True
        poi_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/POI_Submission_Illustration_01.png?cache=1')
        poi_embed.set_footer(text=_('Sent by @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        def check(reply):
            if reply.author is not guild.me and reply.channel.id == channel.id and reply.author == message.author:
                return True
            else:
                return False
        while True:
            async with ctx.typing():
                if checks.is_owner_check(ctx) and len(self.bot.guilds) > 1:
                    poi_embed.clear_fields()
                    poi_embed.add_field(name=_('**Edit Server POIs**'), value=f"Meowth! I'll help you edit a POI!\n\nFirst, I'll need to know what **guild** you would like to edit. By default I will edit **{guild.name}**, would you like to continue with this guild?\n\nReply with **Y** to stay on **{guild.name}** or reply with any of the {len(self.bot.guilds)} **Guild IDs** that I have access to. You can reply with **cancel** to stop anytime.", inline=False)
                    poi_guild_wait = await channel.send(embed=poi_embed)
                    try:
                        poi_guild_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        poi_guild_msg = None
                    await utils.safe_delete(poi_guild_wait)
                    if not poi_guild_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(poi_guild_msg)
                    if poi_guild_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif poi_guild_msg.clean_content.lower() == "y":
                        guild = ctx.guild
                    elif not poi_guild_msg.clean_content.isdigit() or int(poi_guild_msg.clean_content) not in [x.id for x in self.bot.guilds]:
                        error = _("entered an invalid guild")
                        break
                    else:
                        guild = self.bot.get_guild(int(poi_guild_msg.clean_content))
                    first = False
                if target and any([target.lower() == "stop", target.lower() == "gym"]):
                    poi_target = target
                elif not target or (target and not any([target.lower() == "stop", target.lower() == "gym"])):
                    poi_embed.clear_fields()
                    poi_embed.add_field(name=_('**Edit Server POIs**'), value=f"{'Meowth! I will help you edit a POI!' if first else ''}\n\n{'First' if first else 'Meowth! Now'}, I'll need to know what **type** of POI you'd like to modify. Reply with **gym** or **stop**. You can reply with **cancel** to stop anytime.", inline=False)
                    poi_type_wait = await channel.send(embed=poi_embed)
                    try:
                        poi_type_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        poi_type_msg = None
                    await utils.safe_delete(poi_type_wait)
                    if not poi_type_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(poi_type_msg)
                    if poi_type_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif not any([poi_type_msg.clean_content.lower() == "stop", poi_type_msg.clean_content.lower() == "gym"]):
                        error = _("entered an invalid option")
                        break
                    else:
                        poi_target = poi_type_msg.clean_content.lower()
                    first = False
                if action and any([action.lower() == "add", action.lower() == "remove", action.lower() == "list"]):
                    poi_action = action
                elif not action or (action and not any([action.lower() == "add", action.lower() == "remove"])):
                    poi_embed.clear_fields()
                    poi_embed.add_field(name=_('**Edit Server POIs**'), value=f"{'Meowth! I will help you edit a POI!' if first else ''}\n\n{'First' if first else 'Meowth! Now'}, I'll need to know what **action** you'd like to use. Reply with **add**, **remove**, or **list**. You can reply with **cancel** to stop anytime.", inline=False)
                    poi_action_wait = await channel.send(embed=poi_embed)
                    try:
                        poi_action_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        poi_action_msg = None
                    await utils.safe_delete(poi_action_wait)
                    if not poi_action_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(poi_action_msg)
                    if poi_action_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif not any([poi_action_msg.clean_content.lower() == "add", poi_action_msg.clean_content.lower() == "remove", poi_action_msg.clean_content.lower() == "list"]):
                        error = _("entered an invalid option")
                        break
                    else:
                        poi_action = poi_action_msg.clean_content.lower()
                    first = False
                if poi_target == "stop":
                    file_name = 'stop_data.json'
                else:
                    file_name = 'gym_data.json'
                try:
                    with open(os.path.join('data', file_name), 'r') as fd:
                        data = json.load(fd)
                except:
                    data = {}
                test_var = data.setdefault(str(guild.id), {})
                data_keys = [x.lower().strip() for x in data[str(guild.id)].keys() if x]
                if poi_target and poi_action == "list":
                    msg = f"**{poi_target.title()}s for {guild.name} Server as of {timestamp.strftime(_('%B %d, %Y'))}**\n\nAll {poi_target}s can be wanted with {ctx.prefix}want {poi_target} <{poi_target} name>\n\n"
                    for poi in data[str(guild.id)]:
                        poi_coords = data[str(guild.id)][poi]['coordinates']
                        poi_alias = data[str(guild.id)][poi].get('alias', "")
                        poi_notes = data[str(guild.id)][poi].get('notes', "")
                        msg += f"**{poi}**"
                        if poi_alias:
                            msg += f" (*Alias for {poi_alias}*)"
                        msg += f" – Coordinates: {poi_coords}"
                        if poi_notes:
                            msg += f" – Notes: {poi_notes}"
                        msg += "\n"
                    paginator = commands.Paginator(prefix=None, suffix=None)
                    for line in msg.split('\n'):
                        paginator.add_line(line.rstrip())
                    for p in paginator.pages:
                        await ctx.send(p)
                    return
                elif poi_target and poi_action != "list":
                    poi_embed.clear_fields()
                    poi_embed.add_field(name=_('**Edit Server POIs**'), value=f"Meowth! Now I'll need to know the in-game **name** or the **alias** of the {poi_target} you'd like to {poi_action}. Reply with the name of the {poi_target}. You can reply with **cancel** to stop anytime.", inline=False)
                    poi_name_wait = await channel.send(embed=poi_embed)
                    try:
                        poi_name_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        poi_name_msg = None
                    await utils.safe_delete(poi_name_wait)
                    if not poi_name_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(poi_name_msg)
                    if poi_name_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif poi_name_msg.clean_content.lower().strip() not in data_keys and poi_action != "add":
                        error = _("entered a POI not on my **list**")
                        break
                    else:
                        poi_name = poi_name_msg.clean_content
                if poi_target and poi_action == "remove":
                    poi_data_name = list(data[str(guild.id)].keys())[data_keys.index(poi_name.lower())]
                    del data[str(guild.id)][poi_data_name]
                    for k in list(data[str(guild.id)].keys()):
                        if data[str(guild.id)][k].get('alias', None) == poi_data_name:
                            del data[str(guild.id)][k]
                    with open(os.path.join('data', file_name), 'w') as fd:
                        json.dump(data, fd, indent=2, separators=(', ', ': '))
                    break
                elif poi_target and poi_action == "add":
                    poi_embed.clear_fields()
                    poi_embed.add_field(name=_('**Edit Server POIs**'), value=f"Meowth! Now I'll need to know the **coordinates** of the {poi_name} {poi_target} you'd like to {poi_action}. Reply with the coordinates of the {poi_target}. You can reply with **cancel** to stop anytime.", inline=False)
                    poi_coord_wait = await channel.send(embed=poi_embed)
                    try:
                        poi_coord_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        poi_coord_msg = None
                    await utils.safe_delete(poi_coord_wait)
                    if not poi_coord_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(poi_coord_msg)
                    if poi_coord_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif not re.match(r'^\s*-?\d{1,2}\.?\d*,\s*-?\d{1,3}\.?\d*\s*$', poi_coord_msg.clean_content.lower()):
                        error = _("entered something invalid")
                        break
                    else:
                        poi_coords = poi_coord_msg.clean_content.lower().replace(" ", "")
                    poi_embed.clear_fields()
                    poi_embed.add_field(name=_('**Edit Server POIs**'), value=f"Meowth! Is this an **alias** for a {poi_target} you've previously added? Reply with the **N** if not or the in-game name of the of the {poi_target} you've previously added. You can reply with **cancel** to stop anytime.", inline=False)
                    poi_alias_wait = await channel.send(embed=poi_embed)
                    try:
                        poi_alias_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        poi_alias_msg = None
                    await utils.safe_delete(poi_alias_wait)
                    if not poi_alias_wait:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(poi_alias_msg)
                    if poi_alias_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif poi_alias_msg.clean_content.lower() == "n":
                        poi_alias = None
                    elif poi_alias_msg.clean_content.lower().strip() not in data_keys:
                        error = _("entered a POI not on my **list**")
                        break
                    else:
                        poi_alias = list(data[str(guild.id)].keys())[data_keys.index(poi_alias_msg.clean_content.lower())]
                    poi_embed.clear_fields()
                    poi_embed.add_field(name=_('**Edit Server POIs**'), value=f"Meowth! Are there any **notes** you'd like to add to the {poi_name} {poi_target}? Reply with the **N** if not or any notes you'd like to add. You can reply with **cancel** to stop anytime.", inline=False)
                    poi_note_wait = await channel.send(embed=poi_embed)
                    try:
                        poi_note_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        poi_note_msg = None
                    await utils.safe_delete(poi_note_wait)
                    if not poi_note_wait:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(poi_note_msg)
                    if poi_note_wait.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif poi_note_wait.clean_content.lower() == "n":
                        poi_notes = None
                    else:
                        poi_notes = poi_note_wait.clean_content.lower()
                    data[str(guild.id)][poi_name] = {"coordinates":poi_coords}
                    if poi_alias:
                        data[str(guild.id)][poi_name]['alias'] = poi_alias
                    if poi_notes:
                        data[str(guild.id)][poi_name]['notes'] = poi_notes
                    with open(os.path.join('data', file_name), 'w') as fd:
                        json.dump(data, fd, indent=2, separators=(', ', ': '))
                    break
        if error:
            poi_embed.clear_fields()
            poi_embed.add_field(name=_('**POI Edit Cancelled**'), value=_("Meowth! Your edit has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await channel.send(embed=poi_embed, delete_after=10)
            await utils.safe_delete(message)
        else:
            poi_embed.clear_fields()
            poi_embed.add_field(name=_('**POI Edit Completed**'), value=f"Meowth! Your edit completed successfully. {poi_name.title()} has been {poi_action}ed to {poi_target}s.", inline=False)
            confirmation = await channel.send(embed=poi_embed)
            await utils.safe_delete(message)
            self.gym_data = self.init_json()
            self.stop_data = self.init_stop_json()

    @commands.command(hidden=True)
    async def gym_match_test(self, ctx, *, gym_name):
        gyms = self.get_gyms(ctx.guild.id)
        if not gyms:
            await ctx.send('Gym matching has not been set up for this server.')
            return
        match, score = self.poi_match(gym_name, gyms, None)
        if match:
            gym_info = gyms[match]
            coords = gym_info['coordinates']
            notes = gym_info.get('notes', 'No notes for this gym.')
            gym_info_str = (f"**Coordinates:** {coords}\n"
                            f"**Notes:** {notes}")
            await ctx.send(f"Successful match with `{match}` "
                           f"with a score of `{score}`\n{gym_info_str}")
        else:
            await ctx.send("No match found.")

    @commands.command(hidden=True)
    async def stop_match_test(self, ctx, *, stop_name):
        stops = self.get_stops(ctx.guild.id)
        if not stops:
            await ctx.send('Stop matching has not been set up for this server.')
            return
        match, score = self.poi_match(stop_name, None, stops)
        if match:
            stop_info = stops[match]
            coords = stop_info['coordinates']
            notes = stop_info.get('notes', 'No notes for this stop.')
            stop_info_str = (f"**Coordinates:** {coords}\n"
                            f"**Notes:** {notes}")
            await ctx.send(f"Successful match with `{match}` "
                           f"with a score of `{score}`\n{stop_info_str}")
        else:
            await ctx.send("No match found.")

    @commands.command(hidden=True)
    async def whereis(self, ctx, *, poi_name):
        stops = self.get_stops(ctx.guild.id)
        gyms = self.get_gyms(ctx.guild.id)
        if not stops and not gyms:
            await ctx.send('Location matching has not been set up for this server.')
            return
        poi_info, location, poi_url = await self.get_poi_info(ctx, poi_name, "whereis", dupe_check=False)
        if not location:
            return
        if location in gyms:
            match_type = "gym"
        elif location in stops:
            match_type = "stop"
        poi_coords = poi_url.split("query=")[1]
        poi_embed = discord.Embed(colour=ctx.guild.me.colour, description=poi_info).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/POI_Submission_Illustration_01.png?cache=1')
        poi_embed.set_author(name=f"Matched Location", icon_url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/emoji/here.png?cache=1")
        poi_embed.add_field(name="Directions", value=f"[Google Maps](https://www.google.com/maps/search/?api=1&query={poi_coords}) | [Apple Maps](http://maps.apple.com/maps?daddr={poi_coords}&z=10&t=s&dirflg=d) | [Open Street Map](https://www.openstreetmap.org/#map=16/{poi_coords.split(',')[0]}/{poi_coords.split(',')[1]})", inline=False)
        if match_type == "gym":
            active_raids = []
            index = 1
            for channel in self.bot.guild_dict[ctx.guild.id].setdefault('raidchannel_dict', {}):
                if self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][channel].get('address', "") == location:
                    raid_channel = self.bot.get_channel(channel)
                    active_raids.append(f"{index}. {raid_channel.mention}")
                    index += 1
            if active_raids:
                poi_embed.add_field(name="Current Raids", value=('\n').join(active_raids), inline=False)
        elif match_type == "stop":
            active_quests = []
            index = 1
            for report in self.bot.guild_dict[ctx.guild.id].setdefault('questreport_dict', {}):
                if self.bot.guild_dict[ctx.guild.id]['questreport_dict'][report].get('location', "") == location:
                    report_channel = self.bot.get_channel(self.bot.guild_dict[ctx.guild.id]['questreport_dict'][report]['report_channel'])
                    report_message = await report_channel.fetch_message(report)
                    reward = self.bot.guild_dict[ctx.guild.id]['questreport_dict'][report]['reward']
                    active_quests.append(f"{index}. [{reward.title()}]({report_message.jump_url})")
                    index += 1
            if active_quests:
                poi_embed.add_field(name="Current Research", value=('\n').join(active_quests), inline=False)
            active_lures = []
            index = 1
            for report in self.bot.guild_dict[ctx.guild.id].setdefault('lure_dict', {}):
                if self.bot.guild_dict[ctx.guild.id]['lure_dict'][report].get('location', "") == location:
                    report_channel = self.bot.get_channel(self.bot.guild_dict[ctx.guild.id]['lure_dict'][report]['report_channel'])
                    report_message = await report_channel.fetch_message(report)
                    type = self.bot.guild_dict[ctx.guild.id]['lure_dict'][report]['type']
                    active_lures.append(f"{index}. [{type.title()}]({report_message.jump_url})")
                    index += 1
            if active_lures:
                poi_embed.add_field(name="Current Lures", value=('\n').join(active_lures), inline=False)
            active_invasions = []
            index = 1
            for report in self.bot.guild_dict[ctx.guild.id].setdefault('invasion_dict', {}):
                if self.bot.guild_dict[ctx.guild.id]['invasion_dict'][report].get('location', "") == location:
                    report_channel = self.bot.get_channel(self.bot.guild_dict[ctx.guild.id]['invasion_dict'][report]['report_channel'])
                    report_message = await report_channel.fetch_message(report)
                    reward = self.bot.guild_dict[ctx.guild.id]['invasion_dict'][report]['reward']
                    active_invasions.append(f"{index}. [{reward.title()}]({report_message.jump_url})")
                    index += 1
            if active_invasions:
                poi_embed.add_field(name="Current Invasions", value=('\n').join(active_invasions), inline=False)
            active_wilds = []
            index = 1
            for report in self.bot.guild_dict[ctx.guild.id].setdefault('wildreport_dict', {}):
                if self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][report].get('location', "") == location:
                    report_channel = self.bot.get_channel(self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][report]['report_channel'])
                    report_message = await report_channel.fetch_message(report)
                    pokemon = self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][report]['pkmn_obj']
                    active_wilds.append(f"{index}. [{pokemon.title()}]({report_message.jump_url})")
                    index += 1
            if active_wilds:
                poi_embed.add_field(name="Current Wilds", value=('\n').join(active_wilds), inline=False)
        await ctx.send(embed=poi_embed)

    async def poi_match_prompt(self, ctx, poi_name, gyms=None, stops=None):
        channel = ctx.channel
        author = ctx.author
        match, score = self.poi_match(poi_name, gyms, stops)
        if not match:
            return None
        if ctx.author.bot:
            return match
        if score < 80:
            try:
                answer_yes = self.bot.custom_emoji.get('answer_yes', '\u2705')
                answer_no = self.bot.custom_emoji.get('answer_no', '\u274e')
                answer_cancel = self.bot.custom_emoji.get('answer_cancel', '\u274c')
                question = f"{author.mention} Did you mean: **{match}**?\n\nReact with {answer_yes} to match report with **{match}**, {answer_no} to report without matching, or {answer_cancel} to cancel report."
                q_msg = await channel.send(question)
                reaction, __ = await utils.ask(self.bot, q_msg, author.id, react_list=[answer_yes, answer_no, answer_cancel])
            except TypeError:
                await utils.safe_delete(q_msg)
                return None
            if not reaction:
                await utils.safe_delete(q_msg)
                return None
            if reaction.emoji == self.bot.custom_emoji.get('answer_cancel', '\u274c'):
                await utils.safe_delete(q_msg)
                return False
            if reaction.emoji == self.bot.custom_emoji.get('answer_yes', '\u2705'):
                await utils.safe_delete(q_msg)
                return match
            await utils.safe_delete(q_msg)
            return None
        return match

    async def get_poi_info(self, ctx, details, type, dupe_check=True):
        message = ctx.message
        gyms = self.get_gyms(ctx.guild.id)
        stops = self.get_stops(ctx.guild.id)
        pois = {**gyms, **stops}
        poi_info = ""
        match_type = None
        duplicate_raids = []
        duplicate_research = []
        duplicate_invasions = []
        if not gyms and not stops:
            return poi_info, details, False
        if type == "raid" or type == "exraid":
            match = await self.poi_match_prompt(ctx, details, gyms, None)
        elif type == "research" or type == "lure" or type == "invasion":
            match = await self.poi_match_prompt(ctx, details, None, stops)
        elif type == "wild" or type == "pvp" or type == "whereis":
            match = await self.poi_match_prompt(ctx, details, gyms, stops)
        else:
            return poi_info, details, False
        if match == False:
            return poi_info, False, False
        if not match:
            return poi_info, details, False
        if match in gyms:
            match_type = "gym"
        elif match in stops:
            match_type = "stop"
        poi = pois[match]
        details = match
        poi_coords = poi['coordinates']
        poi_note = poi.get('notes', "")
        poi_alias = poi.get('alias', "")
        if poi_note:
            poi_note = f"\n**Notes:** {poi_note}"
        if poi_alias:
            details = poi_alias
        poi_gmaps_link = f"https://www.google.com/maps/search/?api=1&query={poi_coords}"
        if type == "raid" or type == "exraid":
            poi_info = _("**Gym:** {0}{1}").format(details, poi_note)
            for raid in self.bot.guild_dict[ctx.guild.id]['raidchannel_dict']:
                raid_address = self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][raid]['address']
                raid_report_channel = self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][raid]['report_channel']
                if self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][raid]['type'] == "exraid" or self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][raid]['egg_level'] == "EX":
                    raid_type = "exraid"
                else:
                    raid_type = "raid"
                if (details == raid_address) and ctx.channel.id == raid_report_channel and raid_type == type:
                    if message.author.bot:
                        return "", False, False
                    dupe_channel = self.bot.get_channel(raid)
                    if dupe_channel:
                        duplicate_raids.append(dupe_channel.mention)
            if duplicate_raids:
                if ctx.author.bot:
                    return "", False, False
                if not dupe_check:
                    return poi_info, details, poi_gmaps_link
                rusure = await message.channel.send(_('Meowth! It looks like that raid might already be reported.\n\n**Potential Duplicate:** {dupe}\n\nReport anyway?').format(dupe=", ".join(duplicate_raids)))
        elif type == "research":
            poi_info = poi_note
            counter = 1
            for quest in self.bot.guild_dict[ctx.guild.id]['questreport_dict']:
                quest_details = self.bot.guild_dict[ctx.guild.id]['questreport_dict'][quest]
                research_location = quest_details['location']
                research_channel = quest_details['report_channel']
                research_reward = quest_details['reward'].strip()
                research_quest = quest_details['quest'].strip()
                if (details == research_location) and ctx.channel.id == research_channel:
                    if message.author.bot:
                        return "", False, False
                    research_details = f"`{counter}. Pokestop: {research_location} Quest: {research_quest} Reward: {research_reward}`"
                    duplicate_research.append(research_details)
                    counter += 1
            if duplicate_research:
                if ctx.author.bot:
                    return "", False, False
                if not dupe_check:
                    return poi_info, details, poi_gmaps_link
                rusure = await message.channel.send(_('Meowth! It looks like that quest might already be reported.\n\n**Potential Duplicate:** {dupe}\n\nReport anyway?').format(dupe=", ".join(duplicate_research)))
        elif type == "invasion":
            poi_info = poi_note
            counter = 1
            for quest in self.bot.guild_dict[ctx.guild.id]['invasion_dict']:
                inv_details = self.bot.guild_dict[ctx.guild.id]['invasion_dict'][quest]
                invasion_location = inv_details['location']
                invasion_channel = inv_details['report_channel']
                invasion_reward = inv_details['reward'].strip()
                if (details == invasion_location) and ctx.channel.id == invasion_channel:
                    if message.author.bot:
                        return "", False, False
                    invasion_details = f"`{counter}. Pokestop: {invasion_location} Reward: {invasion_reward}`"
                    duplicate_invasions.append(invasion_details)
                    counter += 1
            if duplicate_invasions:
                if ctx.author.bot:
                    return "", False, False
                if not dupe_check:
                    return poi_info, details, poi_gmaps_link
                rusure = await message.channel.send(_('Meowth! It looks like that invasion might already be reported.\n\n**Potential Duplicate:** {dupe}\n\nReport anyway?').format(dupe=", ".join(duplicate_invasions)))
        elif type == "wild" or type == "lure" or type == "pvp" or type == "whereis":
            poi_info = f"**{match_type.title()}:** {details}{poi_note}"
        if duplicate_raids or duplicate_research or duplicate_invasions:
            try:
                timeout = False
                res, reactuser = await utils.ask(self.bot, rusure, message.author.id)
            except TypeError:
                timeout = True
            if timeout or res.emoji == self.bot.custom_emoji.get('answer_no', '\u274e'):
                await utils.safe_delete(rusure)
                confirmation = await message.channel.send(_('Report cancelled.'), delete_after=10)
                await utils.safe_delete(message)
                return "", False, False
            elif res.emoji == self.bot.custom_emoji.get('answer_yes', '\u2705'):
                await utils.safe_delete(rusure)
                return poi_info, details, poi_gmaps_link
            else:
                return "", False, False
        else:
            return poi_info, details, poi_gmaps_link

def setup(bot):
    bot.add_cog(GymMatching(bot))

def teardown(bot):
    bot.remove_cog(GymMatching)
