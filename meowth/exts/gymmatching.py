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
import math
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
        if match and pois[match].get('alias'):
            match = pois[match]['alias']
        return(match, score)

    def haversine_distance(self, origin, destination):
        lat1, lon1 = origin
        lat2, lon2 = destination
        radius = 6371 # km

        dlat = math.radians(lat2-lat1)
        dlon = math.radians(lon2-lon1)
        a = math.sin(dlat/2) * math.sin(dlat/2) + math.cos(math.radians(lat1)) \
            * math.cos(math.radians(lat2)) * math.sin(dlon/2) * math.sin(dlon/2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        d = radius * c
        return d

    async def find_nearest_stop(self, coord, guild_id):
        stops = self.get_stops(guild_id)
        if not stops:
            return None
        search_dict = {self.haversine_distance((float(stops[k]['coordinates'].split(',')[0]), float(stops[k]['coordinates'].split(',')[1])), (float(coord.split(',')[0]), float(coord.split(',')[1]))):k for k,v in stops.items()}
        nearest_stop = min(list(search_dict.keys()))
        nearest_stop = search_dict[nearest_stop]
        if stops[nearest_stop].get('alias'):
            nearest_stop = stops[nearest_stop]['alias']
        return nearest_stop

    async def find_nearest_gym(self, coord, guild_id):
        gyms = self.get_gyms(guild_id)
        if not gyms:
            return None
        search_dict = {self.haversine_distance((float(gyms[k]['coordinates'].split(',')[0]), float(gyms[k]['coordinates'].split(',')[1])), (float(coord.split(',')[0]), float(coord.split(',')[1]))):k for k,v in gyms.items()}
        nearest_gym = min(list(search_dict.keys()))
        nearest_gym = search_dict[nearest_gym]
        if gyms[nearest_gym].get('alias'):
            nearest_gym = gyms[nearest_gym]['alias']
        return nearest_gym

    async def find_nearest_poi(self, coord, guild_id):
        gyms = self.get_gyms(guild_id)
        stops = self.get_stops(guild_id)
        if not gyms and not stops:
            return None
        pois = {**gyms, **stops}
        search_dict = {self.haversine_distance((float(pois[k]['coordinates'].split(',')[0]), float(pois[k]['coordinates'].split(',')[1])), (float(coord.split(',')[0]), float(coord.split(',')[1]))):k for k,v in pois.items()}
        nearest_poi = min(list(search_dict.keys()))
        nearest_poi = search_dict[nearest_poi]
        if pois[nearest_poi].get('alias'):
            nearest_poi = pois[nearest_poi]['alias']
        return nearest_poi

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
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        error = False
        first = True
        poi_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/POI_Submission_Illustration_01.png?cache=1')
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
                    poi_embed.add_field(name=_('**Edit Server POIs**'), value=f"Meowth! I'll help you edit a POI!\n\nFirst, I'll need to know what **guild** you would like to edit. By default I will edit **{guild.name}**, would you like to continue with this guild?\n\nReply with **yes** to stay on **{guild.name}** or reply with any of the {len(self.bot.guilds)} **Guild IDs** that I have access to.\n\n{(', ').join(['**'+str(x.id)+'** - '+x.name for x in self.bot.guilds])}\n\nYou can reply with **cancel** to stop anytime.", inline=False)
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
                    elif "y" in poi_guild_msg.clean_content.lower():
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
                if action and any([action.lower() == "add", action.lower() == "remove", action.lower() == "list", action.lower() == "convert", action.lower() == "edit"]):
                    poi_action = action
                elif not action or (action and not any([action.lower() == "add", action.lower() == "remove", action.lower() == "convert", action.lower() == "edit"])):
                    poi_embed.clear_fields()
                    poi_embed.add_field(name=_('**Edit Server POIs**'), value=f"{'Meowth! I will help you edit a POI!' if first else ''}\n\n{'First' if first else 'Meowth! Now'}, I'll need to know what **action** you'd like to use. Reply with **add**, **remove**, **convert**, **edit**, or **list**. You can reply with **cancel** to stop anytime.", inline=False)
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
                    elif not any([poi_action_msg.clean_content.lower() == "add", poi_action_msg.clean_content.lower() == "remove", poi_action_msg.clean_content.lower() == "list", poi_action_msg.clean_content.lower() == "convert", poi_action_msg.clean_content.lower() == "edit"]):
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
                elif poi_target and poi_action == "convert":
                    convert_dict = {}
                    poi_data_name = list(data[str(guild.id)].keys())[data_keys.index(poi_name.lower())]
                    poi_data_coords = data[str(guild.id)].get(poi_data_name, {}).get('coordinates', "")
                    poi_data_alias = data[str(guild.id)].get(poi_data_name, {}).get('alias', "")
                    poi_data_notes = data[str(guild.id)].get(poi_data_name, {}).get('notes', "")
                    convert_dict[poi_data_name] = {"coordinates": poi_data_coords, "alias": poi_data_alias, "notes": poi_data_alias}
                    del data[str(guild.id)][poi_data_name]
                    for k in list(data[str(guild.id)].keys()):
                        if data[str(guild.id)][k].get('alias', None) == poi_data_name:
                            convert_dict[k] = {"coordinates": data[str(guild.id)][k].get('coordinates'), "alias": data[str(guild.id)][k].get('alias', ""), "notes":data[str(guild.id)][k].get('notes', "")}
                            del data[str(guild.id)][k]
                    with open(os.path.join('data', file_name), 'w') as fd:
                        json.dump(data, fd, indent=2, separators=(', ', ': '))
                    if poi_target == "stop":
                        file_name = 'gym_data.json'
                    else:
                        file_name = 'stop_data.json'
                    try:
                        with open(os.path.join('data', file_name), 'r') as fd:
                            data = json.load(fd)
                    except:
                        data = {}
                    data[str(guild.id)] = {**data[str(guild.id)], **convert_dict}
                    with open(os.path.join('data', file_name), 'w') as fd:
                        json.dump(data, fd, indent=2, separators=(', ', ': '))
                    break
                elif poi_target and (poi_action == "add" or poi_action == "edit"):
                    if poi_action == "add":
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
                    elif poi_action == "edit":
                        poi_name = list(data[str(guild.id)].keys())[data_keys.index(poi_name.lower())]
                        poi_coords = data[str(guild.id)][poi_name]['coordinates']
                    poi_embed.clear_fields()
                    poi_embed.add_field(name=_('**Edit Server POIs**'), value=f"Meowth! Is this an **alias** for a {poi_target} you've previously added? Reply with the **N** if not or the in-game name of the of the {poi_target} you've previously added. You can reply with **cancel** to stop anytime.", inline=False)
                    poi_alias_wait = await channel.send(embed=poi_embed)
                    try:
                        poi_alias_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        poi_alias_msg = None
                    await utils.safe_delete(poi_alias_wait)
                    if not poi_alias_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(poi_alias_msg)
                    if poi_alias_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif poi_alias_msg.clean_content.lower() == "n":
                        poi_alias = ""
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
                    if not poi_note_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(poi_note_msg)
                    if poi_note_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif poi_note_msg.clean_content.lower() == "n":
                        poi_notes = ""
                    else:
                        poi_notes = poi_note_msg.clean_content
                    data[str(guild.id)][poi_name] = {"coordinates":poi_coords, "alias":poi_alias, "notes":poi_notes}
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
            poi_embed.add_field(name=_('**POI Edit Completed**'), value=f"Meowth! Your edit completed successfully. {poi_name.title()} has been {poi_action}{'d' if poi_action == 'remove' else 'ed'} {'from' if poi_action in ['convert', 'remove'] else 'to'} {poi_target}s.", inline=False)
            confirmation = await channel.send(embed=poi_embed)
            await utils.safe_delete(message)
            self.gym_data = self.init_json()
            self.stop_data = self.init_stop_json()

    @commands.command(hidden=True)
    async def gym_match_test(self, ctx, *, gym_name):
        """Tests matching for a gym"""
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
        """Tests matching for a pokestop"""
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

    @commands.command()
    async def whereis(self, ctx, *, poi_name):
        """Matches and shows information for a POI

        Usage: !whereis <POI name>"""
        stops = self.get_stops(ctx.guild.id)
        gyms = self.get_gyms(ctx.guild.id)
        if not stops and not gyms:
            return await ctx.send('Location matching has not been set up for this server.', delete_after=30)
        poi_info, location, poi_url = await self.get_poi_info(ctx, poi_name, "whereis", dupe_check=False)
        if not location:
            return
        if location in gyms:
            match_type = "gym"
        elif location in stops:
            match_type = "stop"
        else:
            return await ctx.send(f"Location not found. Try again.", delete_after=30)
        poi_coords = poi_url.split("query=")[1]
        poi_embed = discord.Embed(colour=ctx.guild.me.colour, description=poi_info).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/POI_Submission_Illustration_01.png?cache=1')
        poi_embed.set_author(name=f"Matched Location", icon_url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/emoji/here.png?cache=1")
        poi_embed.add_field(name="Directions", value=f"[Google Maps](https://www.google.com/maps/search/?api=1&query={poi_coords}) | [Apple Maps](http://maps.apple.com/maps?daddr={poi_coords}&z=10&t=s&dirflg=d) | [Open Street Map](https://www.openstreetmap.org/#map=16/{poi_coords.split(',')[0]}/{poi_coords.split(',')[1]})", inline=False)
        if match_type == "gym":
            active_raids = []
            index = 1
            for channel in self.bot.guild_dict[ctx.guild.id].setdefault('raidchannel_dict', {}):
                if self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][channel].get('address', "") == location:
                    raid_channel = self.bot.get_channel(channel)
                    raid_type = self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][channel].get('reporttype')
                    raid_level = self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][channel].get('egg_level')
                    raid_pokemon = self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][channel].get('pkmn_obj')
                    if raid_pokemon and raid_channel:
                        if channel in self.bot.active_channels:
                            raid_pokemon = self.bot.active_channels[channel]['pokemon']
                        else:
                            raid_pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, raid_pokemon)
                        shiny_str = ""
                        if raid_pokemon and "raid" in raid_pokemon.shiny_available:
                            shiny_str = self.bot.custom_emoji.get('shiny_chance', u'\U00002728') + " "
                        active_raids.append(f"{index}. {shiny_str}{raid_channel.mention} {raid_pokemon.emoji}")
                    else:
                        active_raids.append(f"{index}. {raid_channel.mention}")
                    index += 1
            if active_raids:
                poi_embed.add_field(name="Current Raids", value=('\n').join(active_raids), inline=False)

            active_raids = []
            index = 1
            for alarm_raid in self.bot.guild_dict[ctx.guild.id].setdefault('pokealarm_dict', {}):
                if self.bot.guild_dict[ctx.guild.id]['pokealarm_dict'][alarm_raid].get('gym', "") == location:
                    raid_type = self.bot.guild_dict[ctx.guild.id]['pokealarm_dict'][alarm_raid].get('reporttype')
                    raid_level = self.bot.guild_dict[ctx.guild.id]['pokealarm_dict'][alarm_raid].get('egg_level')
                    raid_pokemon = self.bot.guild_dict[ctx.guild.id]['pokealarm_dict'][alarm_raid].get('pkmn_obj')
                    report_channel = self.bot.get_channel(self.bot.guild_dict[ctx.guild.id]['pokealarm_dict'][alarm_raid]['report_channel'])
                    jump_url = f"https://discordapp.com/channels/{ctx.guild.id}/{report_channel.id}/{alarm_raid}"
                    if raid_pokemon and raid_channel:
                        raid_pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, raid_pokemon)
                        shiny_str = ""
                        if raid_pokemon and "raid" in raid_pokemon.shiny_available:
                            shiny_str = self.bot.custom_emoji.get('shiny_chance', u'\U00002728') + " "
                        active_raids.append(f"{index}. {shiny_str}[{str(raid_pokemon)}]({jump_url}) {raid_pokemon.emoji}")
                    else:
                        active_raids.append(f"{index}. [Level {raid_level} Egg]({jump_url})")
                    index += 1
            if active_raids:
                poi_embed.add_field(name="Unreported Raids", value=('\n').join(active_raids), inline=False)

            active_raids = []
            index = 1
            for channel in self.bot.guild_dict[ctx.guild.id].setdefault('exraidchannel_dict', {}):
                if self.bot.guild_dict[ctx.guild.id]['exraidchannel_dict'][channel].get('address', "") == location:
                    raid_channel = self.bot.get_channel(channel)
                    raid_pokemon = self.bot.guild_dict[ctx.guild.id]['pokealarm_dict'][alarm_raid].get('pkmn_obj')
                    if raid_pokemon and raid_channel:
                        if channel in self.bot.active_channels:
                            raid_pokemon = self.bot.active_channels[channel]['pokemon']
                        else:
                            raid_pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, raid_pokemon)
                        shiny_str = ""
                        if raid_pokemon and "raid" in raid_pokemon.shiny_available:
                            shiny_str = self.bot.custom_emoji.get('shiny_chance', u'\U00002728') + " "
                        active_raids.append(f"{index}. {shiny_str}{raid_channel.mention} {raid_pokemon.emoji}")
                    else:
                        active_raids.append(f"{index}. {raid_channel.mention}")
                    index += 1
            if active_raids:
                poi_embed.add_field(name="Current EX Raids", value=('\n').join(active_raids), inline=False)

        elif match_type == "stop":
            active_quests = []
            index = 1
            candy_emoji = utils.parse_emoji(ctx.guild, self.bot.custom_emoji.get('res_candy', u'\U0001F36C'))
            dust_emoji = utils.parse_emoji(ctx.guild, self.bot.custom_emoji.get('res_dust', u'\U00002b50'))
            berry_emoji = utils.parse_emoji(ctx.guild, self.bot.custom_emoji.get('res_berry', u'\U0001F353'))
            potion_emoji = utils.parse_emoji(ctx.guild, self.bot.custom_emoji.get('res_potion', u'\U0001F48A'))
            revive_emoji = utils.parse_emoji(ctx.guild, self.bot.custom_emoji.get('res_revive', u'\U00002764\U0000fe0f'))
            ball_emoji = utils.parse_emoji(ctx.guild, self.bot.custom_emoji.get('res_ball', u'\U000026be'))
            other_emoji = utils.parse_emoji(ctx.guild, self.bot.custom_emoji.get('res_other', u'\U0001F539'))
            for report in self.bot.guild_dict[ctx.guild.id].setdefault('questreport_dict', {}):
                if self.bot.guild_dict[ctx.guild.id]['questreport_dict'][report].get('location', "") == location:
                    report_channel = self.bot.get_channel(self.bot.guild_dict[ctx.guild.id]['questreport_dict'][report]['report_channel'])
                    jump_url = f"https://discordapp.com/channels/{ctx.guild.id}/{report_channel.id}/{report}"
                    reward = self.bot.guild_dict[ctx.guild.id]['questreport_dict'][report]['reward']
                    reward_item = await utils.get_item(reward)
                    if report in self.bot.active_research:
                        reward_pokemon = self.bot.active_research[report]
                    else:
                        reward_pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, reward)
                    if reward_item[1]:
                        if "cand" in reward_item[1]:
                            active_quests.append(f"{index}. [{reward.title()}]({jump_url}) {candy_emoji}")
                        elif "dust" in reward_item[1]:
                            active_quests.append(f"{index}. [{reward.title()}]({jump_url}) {dust_emoji}")
                        elif "berr" in reward_item[1]:
                            active_quests.append(f"{index}. [{reward.title()}]({jump_url}) {berry_emoji}")
                        elif "potion" in reward_item[1]:
                            active_quests.append(f"{index}. [{reward.title()}]({jump_url}) {potion_emoji}")
                        elif "revive" in reward_item[1]:
                            active_quests.append(f"{index}. [{reward.title()}]({jump_url}) {revive_emoji}")
                        elif "ball" in reward_item[1]:
                            active_quests.append(f"{index}. [{reward.title()}]({jump_url}) {ball_emoji}")
                        else:
                            active_quests.append(f"{index}. [{reward.title()}]({jump_url}) {other_emoji}")
                    elif reward_pokemon:
                        shiny_str = ""
                        if reward_pokemon and "research" in reward_pokemon.shiny_available:
                            shiny_str = self.bot.custom_emoji.get('shiny_chance', u'\U00002728') + " "
                        active_quests.append(f"{index}. {shiny_str}[{reward.title()}]({jump_url}) {reward_pokemon.emoji}")
                    else:
                        active_quests.append(f"{index}. [{reward.title()}]({jump_url}) {other_emoji}")
                    index += 1
            if active_quests:
                poi_embed.add_field(name="Current Research", value=('\n').join(active_quests), inline=False)

            active_lures = []
            index = 1
            normal_emoji = self.bot.custom_emoji.get('normal_lure', self.bot.config.type_id_dict['normal'])
            glacial_emoji = self.bot.custom_emoji.get('glacial_lure', self.bot.config.type_id_dict['ice'])
            mossy_emoji = self.bot.custom_emoji.get('mossy_lure', self.bot.config.type_id_dict['grass'])
            magnetic_emoji = self.bot.custom_emoji.get('normal_lure', self.bot.config.type_id_dict['steel'])
            for report in self.bot.guild_dict[ctx.guild.id].setdefault('lure_dict', {}):
                if self.bot.guild_dict[ctx.guild.id]['lure_dict'][report].get('location', "") == location:
                    report_channel = self.bot.get_channel(self.bot.guild_dict[ctx.guild.id]['lure_dict'][report]['report_channel'])
                    jump_url = f"https://discordapp.com/channels/{ctx.guild.id}/{report_channel.id}/{report}"
                    type = self.bot.guild_dict[ctx.guild.id]['lure_dict'][report]['type']
                    active_lures.append(f"{index}. [{type.title()}]({jump_url}) {normal_emoji if type == 'normal' else ''}{glacial_emoji if type == 'glacial' else ''}{mossy_emoji if type == 'mossy' else ''}{magnetic_emoji if type == 'magnetic' else ''}")
                    index += 1
            if active_lures:
                poi_embed.add_field(name="Current Lures", value=('\n').join(active_lures), inline=False)

            active_invasions = []
            index = 1
            encounter_emoji = utils.parse_emoji(ctx.guild, self.bot.custom_emoji.get('res_encounter', u'\U00002753'))
            for report in self.bot.guild_dict[ctx.guild.id].setdefault('invasion_dict', {}):
                if self.bot.guild_dict[ctx.guild.id]['invasion_dict'][report].get('location', "") == location:
                    reward_list = []
                    report_channel = self.bot.get_channel(self.bot.guild_dict[ctx.guild.id]['invasion_dict'][report]['report_channel'])
                    jump_url = f"https://discordapp.com/channels/{ctx.guild.id}/{report_channel.id}/{report}"
                    reward = self.bot.guild_dict[ctx.guild.id]['invasion_dict'][report]['reward']
                    reward_type = self.bot.guild_dict[ctx.guild.id]['invasion_dict'][report]['reward_type']
                    if reward:
                        if report in self.bot.active_invasions:
                            for reward_pokemon in self.bot.active_invasions[report]:
                                shiny_str = ""
                                if reward_pokemon and "shadow" in reward_pokemon.shiny_available:
                                    shiny_str = self.bot.custom_emoji.get('shiny_chance', u'\U00002728') + " "
                                reward_list.append(f"{shiny_str}[{reward_pokemon.name.title()}]({jump_url}) {reward_pokemon.emoji}")
                        else:
                            for reward_pokemon in reward:
                                reward_pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, reward_pokemon)
                                if not reward_pokemon:
                                    continue
                                    shiny_str = ""
                                if reward_pokemon and "shadow" in reward_pokemon.shiny_available:
                                    shiny_str = self.bot.custom_emoji.get('shiny_chance', u'\U00002728') + " "
                                reward_list.append(f"{shiny_str}[{reward_pokemon.name.title()}]({jump_url}) {reward_pokemon.emoji}")
                    elif reward_type:
                        reward_list.append(f"[{reward_type.title()}]({jump_url}) {self.bot.config.type_id_dict[reward_type.lower()]}")
                    else:
                        reward_list.append(f"Unknown Pokemon {encounter_emoji}")
                    active_invasions.append(f"{index}. {(', ').join(reward_list)}")
                    index += 1
            if active_invasions:
                poi_embed.add_field(name="Current Invasions", value=('\n').join(active_invasions), inline=False)

        active_wilds = []
        index = 1
        for report in self.bot.guild_dict[ctx.guild.id].setdefault('wildreport_dict', {}):
            if self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][report].get('location', "") == location:
                report_channel = self.bot.get_channel(self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][report]['report_channel'])
                jump_url = f"https://discordapp.com/channels/{ctx.guild.id}/{report_channel.id}/{report}"
                pokemon = self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][report]['pkmn_obj']
                if report in self.bot.active_wilds:
                    pokemon = self.bot.active_wilds[report]
                else:
                    pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, pokemon)
                shiny_str = ""
                if pokemon and "wild" in pokemon.shiny_available:
                    shiny_str = self.bot.custom_emoji.get('shiny_chance', u'\U00002728') + " "
                pokemon_iv = self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][report].get('wild_iv', {}).get('percent', None)
                pokemon_level = self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][report].get('level', None)
                pokemon_cp = self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][report].get('cp', None)
                active_wilds.append(f"{index}. {shiny_str}[{str(pokemon).title()}]({jump_url}) {pokemon.emoji}{' | **'+str(pokemon_iv)+'IV**' if pokemon_iv else ''}{' | **Level '+str(pokemon_level)+'**' if pokemon_level else ''}{' | **'+str(pokemon_cp)+'CP**' if pokemon_cp else ''}")
                index += 1
        if active_wilds:
            poi_embed.add_field(name="Current Wilds", value=('\n').join(active_wilds), inline=False)
        await ctx.send(embed=poi_embed)

    async def poi_match_prompt(self, ctx, poi_name, gyms=None, stops=None, autocorrect=True):
        channel = ctx.channel
        author = ctx.author
        match, score = self.poi_match(poi_name, gyms, stops)
        if not match:
            return None
        if ctx.author.bot:
            if score > 80:
                return match
            else:
                return None
        if score < 80:
            if not autocorrect:
                return None
            try:
                if ctx.invoked_with and ("train" in ctx.invoked_with.lower() or "meetup" in ctx.invoked_with.lower()):
                    return False
                answer_yes = self.bot.custom_emoji.get('answer_yes', u'\U00002705')
                answer_no = self.bot.custom_emoji.get('answer_no', u'\U0000274e')
                answer_cancel = self.bot.custom_emoji.get('answer_cancel', u'\U0000274c')
                question = f"{author.mention} Did you mean: **{match}**?\n\nReact with {answer_yes} to match report with **{match}**, {answer_no} to report without matching, or {answer_cancel} to cancel report."
                q_msg = await channel.send(question)
                reaction, __ = await utils.ask(self.bot, q_msg, author.id, react_list=[answer_yes, answer_no, answer_cancel])
            except TypeError:
                await utils.safe_delete(q_msg)
                return None
            if not reaction:
                await utils.safe_delete(q_msg)
                return None
            if reaction.emoji == self.bot.custom_emoji.get('answer_cancel', u'\U0000274c'):
                await utils.safe_delete(q_msg)
                return False
            if reaction.emoji == self.bot.custom_emoji.get('answer_yes', u'\U00002705'):
                await utils.safe_delete(q_msg)
                return match
            await utils.safe_delete(q_msg)
            return None
        return match

    async def get_poi_info(self, ctx, details, type, dupe_check=True, autocorrect=True):
        message = ctx.message
        gyms = self.get_gyms(ctx.guild.id)
        stops = self.get_stops(ctx.guild.id)
        pois = {**gyms, **stops}
        poi_info = ""
        match_type = None
        duplicate_raids = []
        duplicate_research = []
        duplicate_invasions = []
        duplicate_lures = []
        if not gyms and not stops:
            return poi_info, details, False
        if type == "raid" or type == "exraid":
            match = await self.poi_match_prompt(ctx, details, gyms, None, autocorrect)
        elif type == "research" or type == "lure" or type == "invasion":
            match = await self.poi_match_prompt(ctx, details, None, stops, autocorrect)
        elif type == "wild" or type == "pvp" or type == "whereis":
            match = await self.poi_match_prompt(ctx, details, gyms, stops, autocorrect)
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
            for report_dict in self.bot.channel_report_dicts:
                for raid in self.bot.guild_dict[ctx.guild.id].setdefault(report_dict, {}):
                    raid_address = self.bot.guild_dict[ctx.guild.id].get(report_dict, {}).get(raid, {}).get('address', None)
                    raid_report_channel = self.bot.guild_dict[ctx.guild.id].get(report_dict, {}).get(raid, {}).get('report_channel', None)
                    if self.bot.guild_dict[ctx.guild.id].get(report_dict, {}).get(raid, {}).get('type', None) == "exraid" or self.bot.guild_dict[ctx.guild.id].get(report_dict, {}).get(raid, {}).get('egg_level', None) == "EX":
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
                rusure = await message.channel.send(_('Meowth! It looks like that raid might already be reported.\n\n**Potential Duplicate:** {dupe}\n\nReport anyway?').format(dupe="\n".join(duplicate_raids)))
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
                rusure = await message.channel.send(_('Meowth! It looks like that quest might already be reported.\n\n**Potential Duplicate:** {dupe}\n\nReport anyway?').format(dupe="\n".join(duplicate_research)))
        elif type == "invasion":
            poi_info = f"**{match_type.title()}:** {details}{poi_note}"
            counter = 1
            for report in self.bot.guild_dict[ctx.guild.id]['invasion_dict']:
                inv_details = self.bot.guild_dict[ctx.guild.id]['invasion_dict'][report]
                invasion_location = inv_details['location']
                invasion_channel = inv_details['report_channel']
                invasion_reward = (', ').join(inv_details['reward'])
                if not invasion_reward:
                    invasion_reward = inv_details['reward_type']
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
                rusure = await message.channel.send(_('Meowth! It looks like that invasion might already be reported.\n\n**Potential Duplicate:** {dupe}\n\nReport anyway?').format(dupe="\n".join(duplicate_invasions)))
        elif type == "lure":
            poi_info = f"**{match_type.title()}:** {details}{poi_note}"
            counter = 1
            for report in self.bot.guild_dict[ctx.guild.id]['lure_dict']:
                lure_details = self.bot.guild_dict[ctx.guild.id]['lure_dict'][report]
                lure_location = lure_details['location']
                lure_channel = lure_details['report_channel']
                lure_type = lure_details['type'].strip()
                if (details == lure_location) and ctx.channel.id == lure_channel:
                    if message.author.bot:
                        return "", False, False
                    lure_info = f"`{counter}. Pokestop: {lure_location} Type: {lure_type}`"
                    duplicate_lures.append(lure_info)
                    counter += 1
            if duplicate_lures:
                if ctx.author.bot:
                    return "", False, False
                if not dupe_check:
                    return poi_info, details, poi_gmaps_link
                rusure = await message.channel.send(_('Meowth! It looks like that lure might already be reported.\n\n**Potential Duplicate:** {dupe}\n\nReport anyway?').format(dupe="\n".join(duplicate_lures)))
        elif type == "wild" or type == "pvp" or type == "whereis":
            poi_info = f"**{match_type.title()}:** {details}{poi_note}"
        if duplicate_raids or duplicate_research or duplicate_invasions or duplicate_lures:
            try:
                timeout = False
                res, reactuser = await utils.ask(self.bot, rusure, message.author.id)
            except TypeError:
                timeout = True
            if timeout or res.emoji == self.bot.custom_emoji.get('answer_no', u'\U0000274e'):
                await utils.safe_delete(rusure)
                confirmation = await message.channel.send(_('Report cancelled.'), delete_after=10)
                await utils.safe_delete(message)
                return "", False, False
            elif res.emoji == self.bot.custom_emoji.get('answer_yes', u'\U00002705'):
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
