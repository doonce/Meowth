import os
import json
import asyncio
import functools

from discord.ext import commands

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
            egglevel = channel_dict.get('egglevel', 0)
            pokemon = channel_dict.get('pokemon', "")
            boss = channel_dict.get('pkmn_obj', "Egg")
            if egglevel == "0":
                egglevel = utils.get_level(self.bot, pokemon)
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
            test_var = data.setdefault(str(guild_id), {}).setdefault(address, {"total_raids":0, "completed_raids":0, "completed_trainers":0}).setdefault(egglevel, {"total_raids":0, "completed_raids":0, "completed_trainers":0}).setdefault(boss, {"total_raids":0, "completed_raids":0, "completed_trainers":0})
            gym_total = data[str(guild_id)][address]['total_raids'] + 1
            level_total = data[str(guild_id)][address][egglevel]['total_raids'] + 1
            boss_total = data[str(guild_id)][address][egglevel][boss]['total_raids'] + 1
            gym_trainers = data[str(guild_id)][address]['completed_trainers'] + trainers
            level_trainers = data[str(guild_id)][address][egglevel]['completed_trainers'] + trainers
            boss_trainers = data[str(guild_id)][address][egglevel][boss]['completed_trainers'] + trainers
            if trainers:
                gym_complete = data[str(guild_id)][address]['completed_raids'] + 1
                level_complete = data[str(guild_id)][address][egglevel]['completed_raids'] + 1
                boss_complete = data[str(guild_id)][address][egglevel][boss]['completed_raids'] + 1
                data[str(guild_id)][address]['completed_raids'] = gym_complete
                data[str(guild_id)][address][egglevel]['completed_raids'] = level_complete
                data[str(guild_id)][address][egglevel][boss]['completed_raids'] = boss_complete
            data[str(guild_id)][address]['total_raids'] = gym_total
            data[str(guild_id)][address][egglevel]['total_raids'] = level_total
            data[str(guild_id)][address][egglevel][boss]['total_raids'] = boss_total
            data[str(guild_id)][address]['completed_trainers'] = gym_trainers
            data[str(guild_id)][address][egglevel]['completed_trainers'] = level_trainers
            data[str(guild_id)][address][egglevel][boss]['completed_trainers'] = boss_trainers
            with open(os.path.join('data', 'gym_stats.json'), 'w') as fd:
                json.dump(data, fd, indent=2, separators=(', ', ': '))

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
                answer_yes = self.bot.config.get('answer_yes', '\u2705')
                answer_no = self.bot.config.get('answer_no', '\u274e')
                answer_cancel = self.bot.config.get('answer_cancel', '\u274c')
                question = f"{author.mention} Did you mean: **{match}**?\n\nReact with {answer_yes} to match report with **{match}**, {answer_no} to report without matching, or {answer_cancel} to cancel report."
                q_msg = await channel.send(question)
                reaction, __ = await utils.ask(self.bot, q_msg, author.id, react_list=[answer_yes, answer_no, answer_cancel])
            except TypeError:
                await utils.safe_delete(q_msg)
                return None
            if not reaction:
                await utils.safe_delete(q_msg)
                return None
            if reaction.emoji == self.bot.config.get('answer_cancel', '\u274c'):
                await utils.safe_delete(q_msg)
                return False
            if reaction.emoji == self.bot.config.get('answer_yes', '\u2705'):
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
        duplicate_raids = []
        duplicate_research = []
        if not gyms and not stops:
            return poi_info, details, False
        if type == "raid" or type == "exraid":
            match = await self.poi_match_prompt(ctx, details, gyms, None)
        elif type == "research":
            match = await self.poi_match_prompt(ctx, details, None, stops)
        elif type == "wild":
            match = await self.poi_match_prompt(ctx, details, gyms, stops)
        else:
            return poi_info, details, False
        if match == False:
            return poi_info, False, False
        if not match:
            return poi_info, details, False
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
                raid_reportcity = self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][raid]['reportcity']
                if self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][raid]['type'] == "exraid" or self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][raid]['egglevel'] == "EX":
                    raid_type = "exraid"
                else:
                    raid_type = "raid"
                if (details == raid_address) and ctx.channel.id == raid_reportcity and raid_type == type:
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
            poi_info = _("**Stop:** {0}\n{1}").format(details, poi_note)
            for quest in self.bot.guild_dict[ctx.guild.id]['questreport_dict']:
                quest_details = self.bot.guild_dict[ctx.guild.id]['questreport_dict'][quest]
                research_location = quest_details['location']
                research_channel = quest_details['reportchannel']
                research_reward = quest_details['reward'].strip()
                research_quest = quest_details['quest'].strip()
                if (details == research_location) and ctx.channel.id == research_channel:
                    if message.author.bot:
                        return "", False, False
                    research_details = f"`Pokestop: {research_location} Quest: {research_quest} Reward: {research_reward}`"
                    duplicate_research.append(research_details)
            if duplicate_research:
                if ctx.author.bot:
                    return "", False, False
                if not dupe_check:
                    return poi_info, details, poi_gmaps_link
                rusure = await message.channel.send(_('Meowth! It looks like that quest might already be reported.\n\n**Potential Duplicate:** {dupe}\n\nReport anyway?').format(dupe=", ".join(duplicate_research)))
        if duplicate_raids or duplicate_research:
            try:
                timeout = False
                res, reactuser = await utils.ask(self.bot, rusure, message.author.id)
            except TypeError:
                timeout = True
            if timeout or res.emoji == self.bot.config.get('answer_no', '\u274e'):
                await utils.safe_delete(rusure)
                confirmation = await message.channel.send(_('Report cancelled.'), delete_after=10)
                await utils.safe_delete(message)
                return "", False, False
            elif res.emoji == self.bot.config.get('answer_yes', '\u2705'):
                await utils.safe_delete(rusure)
                return poi_info, details, poi_gmaps_link
            else:
                return "", False, False
        else:
            return poi_info, details, poi_gmaps_link

def setup(bot):
    bot.add_cog(GymMatching(bot))
