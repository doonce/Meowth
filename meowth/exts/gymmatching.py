import os
import json
import asyncio
import functools

from discord.ext import commands

from meowth import utils

class GymMatching:
    def __init__(self, bot):
        self.bot = bot
        self.gym_data = self.init_json()
        self.stop_data = self.init_stop_json()

    def init_json(self):
        with open(os.path.join('data', 'gym_data.json')) as fd:
            return json.load(fd)

    def init_stop_json(self):
        with open(os.path.join('data', 'stop_data.json')) as fd:
            return json.load(fd)

    def get_gyms(self, guild_id):
        return self.gym_data.get(str(guild_id))

    def get_stops(self, guild_id):
        return self.stop_data.get(str(guild_id))

    def gym_match(self, gym_name, gyms):
        match, score = utils.get_match(list(gyms.keys()), gym_name)
        if match:
            match = gyms[match].get('alias', match)
        return (match, score)

    def stop_match(self, stop_name, stops):
        match, score = utils.get_match(list(stops.keys()), stop_name)
        if match:
            match = stops[match].get('alias', match)
        return (match, score)

    def find_nearest_stop(self, coord, guild_id):
        stops = self.get_stops(guild_id)
        if not stops:
            return None
        stops = {k: (float(stops[k]["coordinates"].split(",")[0]), float(stops[k]["coordinates"].split(",")[1])) for k,v in stops.items()}
        dist = lambda s, key: (float(s[0]) - float(stops[key][0])) ** 2 + \
                              (float(s[1]) - float(stops[key][1])) ** 2
        return min(stops, key=functools.partial(dist, coord))

    @commands.command(hidden=True)
    async def gym_match_test(self, ctx, gym_name):
        gyms = self.get_gyms(ctx.guild.id)
        if not gyms:
            await ctx.send('Gym matching has not been set up for this server.')
            return
        match, score = self.gym_match(gym_name, gyms)
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

    async def gym_match_prompt(self, ctx, gym_name, gyms):
        channel = ctx.channel
        author = ctx.author
        match, score = self.gym_match(gym_name, gyms)
        if not match:
            return None
        if ctx.bot:
            return match
        if score < 80:
            try:
                question = _("{mention} Did you mean: **{match}**?\n\nReact with {yes_emoji} to match report with **{match}** gym, {no_emoji} to report without matching, or {cancel_emoji} to cancel report.").format(mention=author.mention, match=match, yes_emoji=self.bot.config['answer_yes'],  no_emoji=self.bot.config['answer_no'],  cancel_emoji=self.bot.config['answer_cancel'], )
                q_msg = await channel.send(question)
                reaction, __ = await utils.ask(self.bot, q_msg, author.id, react_list=[self.bot.config['answer_yes'], self.bot.config['answer_no'], self.bot.config['answer_cancel']])
            except TypeError:
                await utils.safe_delete(q_msg)
                return None
            if not reaction:
                await utils.safe_delete(q_msg)
                return None
            if reaction.emoji == self.bot.config['answer_cancel']:
                await utils.safe_delete(q_msg)
                return False
            if reaction.emoji == self.bot.config['answer_yes']:
                await utils.safe_delete(q_msg)
                return match
            await utils.safe_delete(q_msg)
            return None
        return match

    async def stop_match_prompt(self, ctx, stop_name, stops):
        channel = ctx.channel
        author = ctx.author
        match, score = self.stop_match(stop_name, stops)
        if not match:
            return None
        if ctx.bot:
            return match
        if score < 80:
            try:
                question = _("{mention} Did you mean: **{match}**?\n\nReact with {yes_emoji} to match report with **{match}** stop, {no_emoji} to report without matching, or {cancel_emoji} to cancel report.").format(mention=author.mention, match=match, yes_emoji=self.bot.config['answer_yes'],  no_emoji=self.bot.config['answer_no'],  cancel_emoji=self.bot.config['answer_cancel'], )
                q_msg = await channel.send(question)
                reaction, __ = await utils.ask(self.bot, q_msg, author.id, react_list=[self.bot.config['answer_yes'], self.bot.config['answer_no'], self.bot.config['answer_cancel']])
            except TypeError:
                await utils.safe_delete(q_msg)
                return None
            if not reaction:
                await utils.safe_delete(q_msg)
                return None
            if reaction.emoji == self.bot.config['answer_cancel']:
                await utils.safe_delete(q_msg)
                return False
            if reaction.emoji == self.bot.config['answer_yes']:
                await utils.safe_delete(q_msg)
                return match
            await utils.safe_delete(q_msg)
            return None
        return match

    async def get_gym_info(self, ctx, raid_details, type):
        message = ctx.message
        gyms = self.get_gyms(ctx.guild.id)
        gym_info = ""
        if not gyms:
            return gym_info, raid_details, False
        match = await self.gym_match_prompt(ctx, raid_details, gyms)
        if match == False:
            return gym_info, False, False
        if not match:
            return gym_info, raid_details, False
        else:
            gym = gyms[match]
            raid_details = match
            gym_coords = gym['coordinates']
            gym_note = gym.get('notes', "")
            gym_alias = gym.get('alias', "")
            if gym_note:
                gym_note = f"**Notes:** {gym_note}"
            if gym_alias:
                raid_details = gym_alias
            raid_gmaps_link = f"https://www.google.com/maps/search/?api=1&query={gym_coords}"
            gym_info = _("**Gym:** {0}\n{1}").format(raid_details, gym_note)
            duplicate_raids = []
            for raid in self.bot.guild_dict[message.guild.id]['raidchannel_dict']:
                raid_address = self.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid]['address']
                raid_reportcity = self.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid]['reportcity']
                if self.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid]['type'] == "exraid" or self.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid]['egglevel'] == "EX":
                    raid_type = "exraid"
                else:
                    raid_type = "raid"
                if (raid_details == raid_address) and message.channel.id == raid_reportcity and raid_type == type:
                    if message.author.bot:
                        return "", False, False
                    dupe_channel = self.bot.get_channel(raid)
                    if dupe_channel:
                        duplicate_raids.append(dupe_channel.mention)
            if duplicate_raids:
                if ctx.author.bot:
                    return "", False, False
                rusure = await message.channel.send(_('Meowth! It looks like that raid might already be reported.\n\n**Potential Duplicate:** {dupe}\n\nReport anyway?').format(dupe=", ".join(duplicate_raids)))
                try:
                    timeout = False
                    res, reactuser = await utils.ask(self.bot, rusure, message.author.id)
                except TypeError:
                    timeout = True
                if timeout or res.emoji == self.bot.config['answer_no']:
                    await utils.safe_delete(rusure)
                    confirmation = await message.channel.send(_('Report cancelled.'), delete_after=10)
                    await utils.safe_delete(message)
                    return "", False, False
                elif res.emoji == self.bot.config['answer_yes']:
                    await utils.safe_delete(rusure)
                    return gym_info, raid_details, raid_gmaps_link
                else:
                    return "", False, False
            else:
                return gym_info, raid_details, raid_gmaps_link

    async def get_stop_info(self, ctx, stop_details):
        message = ctx.message
        stops = self.get_stops(ctx.guild.id)
        stop_info = ""
        if not stops:
            return stop_info, stop_details, False
        match = await self.stop_match_prompt(ctx, stop_details, stops)
        if match == False:
            return stop_info, False, False
        if not match:
            return stop_info, stop_details, False
        else:
            stop = stops[match]
            stop_details = match
            stop_coords = stop['coordinates']
            stop_note = stop.get('notes', "")
            stop_alias = stop.get('alias', "")
            if stop_note:
                stop_note = f"**Notes:** {stop_note}"
            if stop_alias:
                stop_details = stop_alias
            stop_gmaps_link = f"https://www.google.com/maps/search/?api=1&query={stop_coords}"
            stop_info = _("**Stop:** {0}\n{1}").format(stop_details, stop_note)
            duplicate_research = []
            for quest in self.bot.guild_dict[message.guild.id]['questreport_dict']:
                quest_details = self.bot.guild_dict[message.guild.id]['questreport_dict'][quest]
                research_location = quest_details['location']
                research_channel = quest_details['reportchannel']
                research_reward = quest_details['reward'].strip()
                research_quest = quest_details['quest'].strip()
                if (stop_details == research_location) and message.channel.id == research_channel:
                    if message.author.bot:
                        return "", False, False
                    research_details = f"`Pokestop: {research_location} Quest: {research_quest} Reward: {research_reward}`"
                    duplicate_research.append(research_details)
            if duplicate_research:
                if ctx.author.bot:
                    return "", False, False
                rusure = await message.channel.send(_('Meowth! It looks like that quest might already be reported.\n\n**Potential Duplicate:** {dupe}\n\nReport anyway?').format(dupe=", ".join(duplicate_research)))
                try:
                    timeout = False
                    res, reactuser = await utils.ask(self.bot, rusure, message.author.id)
                except TypeError:
                    timeout = True
                if timeout or res.emoji == self.bot.config['answer_no']:
                    await utils.safe_delete(rusure)
                    confirmation = await message.channel.send(_('Report cancelled.'), delete_after=10)
                    await utils.safe_delete(message)
                    return "", False, False
                elif res.emoji == self.bot.config['answer_yes']:
                    await utils.safe_delete(rusure)
                    return stop_info, stop_details, stop_gmaps_link
                else:
                    return "", False, False
            else:
                return stop_info, stop_details, stop_gmaps_link

def setup(bot):
    bot.add_cog(GymMatching(bot))
