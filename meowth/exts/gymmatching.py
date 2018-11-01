import os
import json
import asyncio

from discord.ext import commands

from meowth import utils

class GymMatching:
    def __init__(self, bot):
        self.bot = bot
        self.gym_data = self.init_json()

    def init_json(self):
        with open(os.path.join('data', 'gym_data.json')) as fd:
            return json.load(fd)

    def get_gyms(self, guild_id):
        return self.gym_data.get(str(guild_id))

    def gym_match(self, gym_name, gyms):
        match, score = utils.get_match(list(gyms.keys()), gym_name)
        if match:
            match = gyms[match].get('alias', match)
        return (match, score)

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
        if score < 80:
            try:
                question = _("{mention} Did you mean: **{match}**?\n\nReact with ✅ to match report with **{match}** gym, ❎ to report without matching, or ❌ to cancel report.").format(mention=author.mention, match=match)
                q_msg = await channel.send(question)
                reaction, __ = await utils.ask(self.bot, q_msg, author.id, react_list=['✅', '❎','❌'])
            except TypeError:
                await q_msg.delete()
                return None
            if not reaction:
                await q_msg.delete()
                return None
            if reaction.emoji == '❌':
                await q_msg.delete()
                return False
            if reaction.emoji == '✅':
                await q_msg.delete()
                return match
            await q_msg.delete()
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
            raid_gmaps_link = "https://www.google.com/maps/dir/Current+Location/{0}".format(gym_coords)
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
                rusure = await message.channel.send(_('Meowth! It looks like that raid might already be reported.\n\n**Potential Duplicate:** {dupe}\n\nReport anyway?').format(dupe=", ".join(duplicate_raids)))
                try:
                    timeout = False
                    res, reactuser = await utils.ask(self.bot, rusure, message.author.id)
                except TypeError:
                    timeout = True
                if timeout or res.emoji == '❎':
                    await rusure.delete()
                    confirmation = await message.channel.send(_('Report cancelled.'))
                    try:
                        await message.delete()
                    except (discord.errors.Forbidden, discord.errors.HTTPException):
                        pass
                    await asyncio.sleep(10)
                    await confirmation.delete()
                    return "", False, False
                elif res.emoji == '✅':
                    await rusure.delete()
                    return gym_info, raid_details, raid_gmaps_link
                else:
                    return "", False, False
            else:
                return gym_info, raid_details, raid_gmaps_link

def setup(bot):
    bot.add_cog(GymMatching(bot))
