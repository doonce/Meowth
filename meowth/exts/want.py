import asyncio
import copy
import re
import time
import datetime
import dateparser
import textwrap
import logging

import discord
from discord.ext import commands

from meowth import checks
from meowth.exts import pokemon as pkmn_class
from meowth.exts import utilities as utils

logger = logging.getLogger("meowth")

class Want(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(case_insensitive=True, invoke_without_command=True)
    @checks.allowwant()
    async def want(self, ctx, *, pokemon):
        """Add a Pokemon to your wanted list. Currently used for wild, raid, research, nest reports.

        Usage: !want <species>
        Meowth will mention you if anyone reports seeing
        this species in their !wild or !raid command."""

        """Behind the scenes, Meowth tracks user !wants by
        storing information in a database."""
        await ctx.trigger_typing()
        message = ctx.message
        guild = message.guild
        channel = message.channel
        want_split = pokemon.lower().split(',')
        want_list = []
        added_count = 0
        spellcheck_dict = {}
        spellcheck_list = []
        already_want_count = 0
        already_want_list = []
        added_list = []
        role_list = []
        user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('wants', [])
        user_link = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('settings', {}).setdefault('link', True)
        for entered_want in want_split:
            pokemon = pkmn_class.Pokemon.get_pokemon(ctx.bot, entered_want.strip())
            if pokemon:
                want_list.append(pokemon.name.lower())
            elif len(want_split) == 1 and "list" in entered_want:
                await utils.safe_delete(ctx.message)
                list_command = self.bot.get_command("list")
                want_command = list_command.all_commands.get('wants')
                await want_command.invoke(ctx)
                return
            else:
                spellcheck_list.append(entered_want)
                match, score = utils.get_match(ctx.bot.pkmn_list, entered_want)
                spellcheck_dict[entered_want] = match
        for entered_want in want_list:
            role_str = ""
            if entered_want in self.bot.raid_list and user_link:
                role = discord.utils.get(guild.roles, name=entered_want)
                if not role:
                    try:
                        role = await guild.create_role(name = entered_want.lower(), hoist = False, mentionable = True)
                    except discord.errors.HTTPException:
                        await message.channel.send(_('Maximum guild roles reached. Pokemon not added.'), delete_after=10)
                        return
                    await asyncio.sleep(0.5)
                if role not in ctx.author.roles:
                    role_list.append(role)
                role_str = f" ({role.mention})"
            if utils.get_number(self.bot, entered_want) in user_wants:
                already_want_list.append(entered_want.capitalize())
                already_want_count += 1
            else:
                user_wants.append(utils.get_number(self.bot, entered_want))
                added_list.append(f"{entered_want.capitalize()}{role_str}")
                added_count += 1
        await ctx.author.add_roles(*role_list)
        want_count = added_count + already_want_count + len(spellcheck_dict)
        confirmation_msg = _('Meowth! {member}, out of your total **{count}** pokemon:\n').format(member=ctx.author.display_name, count=want_count)
        if added_count > 0:
            confirmation_msg += _('\n**{added_count} Added:** \n\t{added_list}').format(added_count=added_count, added_list=', '.join(added_list))
        if already_want_count > 0:
            confirmation_msg += _('\n**{already_want_count} Already Wanted:** \n\t{already_want_list}').format(already_want_count=already_want_count, already_want_list=', '.join(already_want_list))
        if spellcheck_dict:
            spellcheckmsg = ''
            for word in spellcheck_dict:
                spellcheckmsg += _('\n\t{word}').format(word=word)
                if spellcheck_dict[word]:
                    spellcheckmsg += _(': *({correction}?)*').format(correction=spellcheck_dict[word])
            confirmation_msg += _('\n**{count} Not Valid:**').format(count=len(spellcheck_dict)) + spellcheckmsg
        want_confirmation = await channel.send(embed=discord.Embed(description=confirmation_msg, colour=ctx.me.colour))
        if "tutorial" not in ctx.channel.name.lower():
            await asyncio.sleep(90)
        await utils.safe_delete(want_confirmation)
        await ctx.message.add_reaction(self.bot.config['command_done'])

    @want.command(name='boss')
    @checks.allowwant()
    async def want_boss(self, ctx, *, bosses):
        """Adds a boss role to your wants. Currently used for raid reports.

        Usage: !want boss <boss list>"""
        await ctx.trigger_typing()
        message = ctx.message
        guild = message.guild
        channel = message.channel
        want_split = bosses.lower().split(',')
        want_list = []
        added_count = 0
        spellcheck_dict = {}
        spellcheck_list = []
        already_want_count = 0
        already_want_list = []
        added_list = []
        role_list = []
        user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('bosses', [])
        user_link = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('settings', {}).setdefault('link', True)
        if user_link:
            await message.channel.send(f"{ctx.author.mention} - Your boss list is linked to your want list, please use **!want** to add pokemon.")
            return
        for entered_want in want_split:
            pokemon = pkmn_class.Pokemon.get_pokemon(ctx.bot, entered_want.strip())
            if pokemon:
                want_list.append(pokemon.name.lower())
            else:
                spellcheck_list.append(entered_want)
                match, score = utils.get_match(ctx.bot.pkmn_list, entered_want)
                spellcheck_dict[entered_want] = match
        for entered_want in want_list:
            role_str = ""
            if entered_want in self.bot.raid_list:
                role = discord.utils.get(guild.roles, name=entered_want)
                if not role:
                    try:
                        role = await guild.create_role(name = entered_want.lower(), hoist = False, mentionable = True)
                    except discord.errors.HTTPException:
                        await message.channel.send(_('Maximum guild roles reached. Pokemon not added.'), delete_after=10)
                        return
                    await asyncio.sleep(0.5)
                if role not in ctx.author.roles:
                    role_list.append(role)
                role_str = f" ({role.mention})"
            if utils.get_number(self.bot, entered_want) in user_wants:
                already_want_list.append(entered_want.capitalize())
                already_want_count += 1
            else:
                user_wants.append(utils.get_number(self.bot, entered_want))
                added_list.append(f"{entered_want.capitalize()}{role_str}")
                added_count += 1
        await ctx.author.add_roles(*role_list)
        want_count = added_count + already_want_count + len(spellcheck_dict)
        confirmation_msg = _('Meowth! {member}, out of your total **{count}** boss{s}:\n').format(member=ctx.author.display_name, count=want_count, s="es" if want_count > 1 else "")
        if added_count > 0:
            confirmation_msg += _('\n**{added_count} Added:** \n\t{added_list}').format(added_count=added_count, added_list=', '.join(added_list))
        if already_want_count > 0:
            confirmation_msg += _('\n**{already_want_count} Already Wanted:** \n\t{already_want_list}').format(already_want_count=already_want_count, already_want_list=', '.join(already_want_list))
        if spellcheck_dict:
            spellcheckmsg = ''
            for word in spellcheck_dict:
                spellcheckmsg += _('\n\t{word}').format(word=word)
                if spellcheck_dict[word]:
                    spellcheckmsg += _(': *({correction}?)*').format(correction=spellcheck_dict[word])
            confirmation_msg += _('\n**{count} Not Valid:**').format(count=len(spellcheck_dict)) + spellcheckmsg
        want_confirmation = await channel.send(embed=discord.Embed(description=confirmation_msg, colour=ctx.me.colour))
        if "tutorial" not in ctx.channel.name.lower():
            await asyncio.sleep(90)
        await utils.safe_delete(want_confirmation)
        await ctx.message.add_reaction(self.bot.config['command_done'])

    @want.command(name='gym')
    @checks.allowwant()
    async def want_gym(self, ctx, *, gyms):
        """Add a gym to your want list. Currently used for raid and raid egg reports.

        Usage: !want gym <gym list>"""
        await ctx.trigger_typing()
        message = ctx.message
        guild = message.guild
        channel = message.channel
        want_split = gyms.lower().split(',')
        want_list = []
        added_count = 0
        spellcheck_dict = {}
        spellcheck_list = []
        already_want_count = 0
        already_want_list = []
        added_list = []
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        if not gym_matching_cog:
            return
        gyms = gym_matching_cog.get_gyms(ctx.guild.id)
        user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('gyms', [])
        for entered_want in want_split:
            gym = await gym_matching_cog.poi_match_prompt(ctx, entered_want, gyms, None)
            if gym:
                want_list.append(gym.lower())
            else:
                spellcheck_list.append(entered_want)
                match, score = utils.get_match(gyms.keys(), entered_want)
                spellcheck_dict[entered_want] = match
        for entered_want in want_list:
            if entered_want.lower() in user_wants:
                already_want_list.append(entered_want.title())
                already_want_count += 1
            else:
                user_wants.append(entered_want.lower())
                added_list.append(f"{entered_want.title()}")
                added_count += 1
        want_count = added_count + already_want_count + len(spellcheck_dict)
        confirmation_msg = _('Meowth! {member}, out of your total **{count}** gym{s}:\n').format(member=ctx.author.display_name, count=want_count, s="s" if want_count > 1 else "")
        if added_count > 0:
            confirmation_msg += _('\n**{added_count} Added:** \n\t{added_list}').format(added_count=added_count, added_list=', '.join(added_list))
        if already_want_count > 0:
            confirmation_msg += _('\n**{already_want_count} Already Wanted:** \n\t{already_want_list}').format(already_want_count=already_want_count, already_want_list=', '.join(already_want_list))
        if spellcheck_dict:
            spellcheckmsg = ''
            for word in spellcheck_dict:
                spellcheckmsg += _('\n\t{word}').format(word=word)
                if spellcheck_dict[word]:
                    spellcheckmsg += _(': *({correction}?)*').format(correction=spellcheck_dict[word])
            confirmation_msg += _('\n**{count} Not Valid:**').format(count=len(spellcheck_dict)) + spellcheckmsg
        want_confirmation = await channel.send(embed=discord.Embed(description=confirmation_msg, colour=ctx.me.colour))
        await asyncio.sleep(90)
        await utils.safe_delete(want_confirmation)
        await ctx.message.add_reaction(self.bot.config['command_done'])

    @want.command(name='stop')
    @checks.allowwant()
    async def want_stop(self, ctx, *, stops):
        """Add a gym to your want list. Currently used for wild and research reports.

        Usage: !want stop <stop list>"""
        await ctx.trigger_typing()
        message = ctx.message
        guild = message.guild
        channel = message.channel
        want_split = stops.lower().split(',')
        want_list = []
        added_count = 0
        spellcheck_dict = {}
        spellcheck_list = []
        already_want_count = 0
        already_want_list = []
        added_list = []
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        if not gym_matching_cog:
            return
        stops = gym_matching_cog.get_stops(ctx.guild.id)
        user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('stops', [])
        for entered_want in want_split:
            stop = await gym_matching_cog.poi_match_prompt(ctx, entered_want, None, stops)
            if stop:
                want_list.append(stop.lower())
            else:
                spellcheck_list.append(entered_want)
                match, score = utils.get_match(stops.keys(), entered_want)
                spellcheck_dict[entered_want] = match
        for entered_want in want_list:
            if entered_want.lower() in user_wants:
                already_want_list.append(entered_want.title())
                already_want_count += 1
            else:
                user_wants.append(entered_want.lower())
                added_list.append(f"{entered_want.title()}")
                added_count += 1
        want_count = added_count + already_want_count + len(spellcheck_dict)
        confirmation_msg = _('Meowth! {member}, out of your total **{count}** stop{s}:\n').format(member=ctx.author.display_name, count=want_count, s="s" if want_count > 1 else "")
        if added_count > 0:
            confirmation_msg += _('\n**{added_count} Added:** \n\t{added_list}').format(added_count=added_count, added_list=', '.join(added_list))
        if already_want_count > 0:
            confirmation_msg += _('\n**{already_want_count} Already Wanted:** \n\t{already_want_list}').format(already_want_count=already_want_count, already_want_list=', '.join(already_want_list))
        if spellcheck_dict:
            spellcheckmsg = ''
            for word in spellcheck_dict:
                spellcheckmsg += _('\n\t{word}').format(word=word)
                if spellcheck_dict[word]:
                    spellcheckmsg += _(': *({correction}?)*').format(correction=spellcheck_dict[word])
            confirmation_msg += _('\n**{count} Not Valid:**').format(count=len(spellcheck_dict)) + spellcheckmsg
        want_confirmation = await channel.send(embed=discord.Embed(description=confirmation_msg, colour=ctx.me.colour))
        await asyncio.sleep(90)
        await utils.safe_delete(want_confirmation)
        await ctx.message.add_reaction(self.bot.config['command_done'])

    @want.command(name='item')
    @checks.allowwant()
    async def want_item(self, ctx, *, items):
        """Add a item to your want list. Currently used research reports.

        Item List = incense, poke ball, great ball, ultra ball, master ball, potion, super potion, hyper potion, max potion, revive, max revive, razz berry, golden razz berry, nanab berry, pinap berry, silver pinap berry, fast tm, charged tm, rare candy, lucky egg, stardust, lure module, star piece, premium raid pass, egg incubator, super incubator, team medallion, sun stone, metal coat, dragon scale, up-grade, sinnoh stone

        Usage: !want item <item list>"""
        await ctx.trigger_typing()
        message = ctx.message
        guild = message.guild
        channel = message.channel
        want_split = items.lower().split(',')
        want_list = []
        added_count = 0
        spellcheck_dict = {}
        spellcheck_list = []
        already_want_count = 0
        already_want_list = []
        added_list = []
        item_list = ["incense", "poke ball", "great ball", "ultra ball", "master ball", "potion", "super potion", "hyper potion", "max potion", "revive", "max revive", "razz berry", "golden razz berry", "nanab berry", "pinap berry", "silver pinap berry", "fast tm", "charged tm", "rare candy", "lucky egg", "stardust", "lure module", "star piece", "premium raid pass", "egg incubator", "super incubator", "team medallion", "sun stone", "metal coat", "dragon scale", "up-grade", "sinnoh stone"]
        user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('items', [])
        for entered_want in want_split:
            if entered_want.strip().lower() in item_list:
                want_list.append(entered_want.strip().lower())
            else:
                spellcheck_list.append(entered_want)
                match, score = utils.get_match(item_list, entered_want)
                spellcheck_dict[entered_want] = match
        for entered_want in want_list:
            if entered_want.lower() in user_wants:
                already_want_list.append(entered_want.title())
                already_want_count += 1
            else:
                user_wants.append(entered_want.lower())
                added_list.append(f"{entered_want.title()}")
                added_count += 1
        want_count = added_count + already_want_count + len(spellcheck_dict)
        confirmation_msg = _('Meowth! {member}, out of your total **{count}** item{s}:\n').format(member=ctx.author.display_name, count=want_count, s="s" if want_count > 1 else "")
        if added_count > 0:
            confirmation_msg += _('\n**{added_count} Added:** \n\t{added_list}').format(added_count=added_count, added_list=', '.join(added_list))
        if already_want_count > 0:
            confirmation_msg += _('\n**{already_want_count} Already Wanted:** \n\t{already_want_list}').format(already_want_count=already_want_count, already_want_list=', '.join(already_want_list))
        if spellcheck_dict:
            spellcheckmsg = ''
            for word in spellcheck_dict:
                spellcheckmsg += _('\n\t{word}').format(word=word)
                if spellcheck_dict[word]:
                    spellcheckmsg += _(': *({correction}?)*').format(correction=spellcheck_dict[word])
            confirmation_msg += _('\n**{count} Not Valid:**').format(count=len(spellcheck_dict)) + spellcheckmsg
        want_confirmation = await channel.send(embed=discord.Embed(description=confirmation_msg, colour=ctx.me.colour))
        await asyncio.sleep(90)
        await utils.safe_delete(want_confirmation)
        await ctx.message.add_reaction(self.bot.config['command_done'])

    @want.command(name='type')
    @checks.allowwant()
    async def want_type(self, ctx, *, types):
        """Add a pokemon type to your want list. Currently used for wild, research, nest reports.

        Usage: !want type <type list>"""
        await ctx.trigger_typing()
        message = ctx.message
        guild = message.guild
        channel = message.channel
        want_split = types.lower().split(',')
        want_list = []
        added_count = 0
        spellcheck_dict = {}
        spellcheck_list = []
        already_want_count = 0
        already_want_list = []
        added_list = []
        type_list = ["normal", "fighting", "flying", "poison", "ground", "rock", "bug", "ghost", "steel", "fire", "water", "grass", "electric", "psychic", "ice", "dragon", "dark", "fairy"]
        user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('types', [])
        for entered_want in want_split:
            if entered_want.strip().lower() in type_list:
                want_list.append(entered_want.strip().lower())
            else:
                spellcheck_list.append(entered_want)
                match, score = utils.get_match(type_list, entered_want)
                spellcheck_dict[entered_want] = match
        for entered_want in want_list:
            if entered_want.lower() in user_wants:
                already_want_list.append(entered_want.title())
                already_want_count += 1
            else:
                user_wants.append(entered_want.lower())
                added_list.append(f"{entered_want.title()}")
                added_count += 1
        want_count = added_count + already_want_count + len(spellcheck_dict)
        confirmation_msg = _('Meowth! {member}, out of your total **{count}** type{s}:\n').format(member=ctx.author.display_name, count=want_count, s="s" if want_count > 1 else "")
        if added_count > 0:
            confirmation_msg += _('\n**{added_count} Added:** \n\t{added_list}').format(added_count=added_count, added_list=', '.join(added_list))
        if already_want_count > 0:
            confirmation_msg += _('\n**{already_want_count} Already Wanted:** \n\t{already_want_list}').format(already_want_count=already_want_count, already_want_list=', '.join(already_want_list))
        if spellcheck_dict:
            spellcheckmsg = ''
            for word in spellcheck_dict:
                spellcheckmsg += _('\n\t{word}').format(word=word)
                if spellcheck_dict[word]:
                    spellcheckmsg += _(': *({correction}?)*').format(correction=spellcheck_dict[word])
            confirmation_msg += _('\n**{count} Not Valid:**').format(count=len(spellcheck_dict)) + spellcheckmsg
        want_confirmation = await channel.send(embed=discord.Embed(description=confirmation_msg, colour=ctx.me.colour))
        await asyncio.sleep(90)
        await utils.safe_delete(want_confirmation)
        await ctx.message.add_reaction(self.bot.config['command_done'])

    @want.command(name='iv', aliases=['ivs'])
    @checks.allowwant()
    async def want_iv(self, ctx, *, ivs):
        """Add a IV to your want list. Currently used for wild reports.

        Usage: !want iv <iv list>
        Enter individual numbers or iv+ to add iv to 100"""
        await ctx.trigger_typing()
        message = ctx.message
        guild = message.guild
        channel = message.channel
        want_split = ivs.lower().split(',')
        want_list = []
        added_count = 0
        already_want_count = 0
        already_want_list = []
        added_list = []
        error_list = []
        user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('ivs', [])
        for entered_want in want_split:
            if "+" in entered_want.lower():
                entered_want = entered_want.replace("+", "").strip()
                if not entered_want.strip().isdigit():
                    error_list.append(entered_want)
                    continue
                for iv in range(int(entered_want), 101):
                    if iv not in want_list:
                        want_list.append(str(iv))
            else:
                if not entered_want.strip().isdigit():
                    error_list.append(entered_want)
                    continue
                if entered_want not in want_list:
                    want_list.append(entered_want)
        for entered_want in want_list:
            if int(entered_want) in user_wants:
                already_want_list.append(entered_want)
                already_want_count += 1
            else:
                user_wants.append(int(entered_want))
                added_list.append(f"{entered_want}")
                added_count += 1
        want_count = added_count + already_want_count + len(error_list)
        confirmation_msg = _('Meowth! {member}, out of your total **{count}** iv{s}:\n').format(member=ctx.author.display_name, count=want_count, s="s" if want_count > 1 else "")
        if added_count > 0:
            confirmation_msg += _('\n**{added_count} Added:** \n\t{added_list}').format(added_count=added_count, added_list=', '.join(added_list))
        if already_want_count > 0:
            confirmation_msg += _('\n**{already_want_count} Already Wanted:** \n\t{already_want_list}').format(already_want_count=already_want_count, already_want_list=', '.join(already_want_list))
        if error_list:
            error_msg = ''
            for word in error_list:
                error_msg += _('\n\t{word}').format(word=word)
            confirmation_msg += _('\n**{count} Not Valid:**').format(count=len(error_list)) + error_msg
        want_confirmation = await channel.send(embed=discord.Embed(description=confirmation_msg, colour=ctx.me.colour))
        await asyncio.sleep(90)
        await utils.safe_delete(want_confirmation)
        await ctx.message.add_reaction(self.bot.config['command_done'])

    @want.command()
    @checks.allowwant()
    async def settings(self, ctx):
        """Changes alert settings such as muting and active hours.

        Usage: !want settings"""
        await ctx.trigger_typing()
        mute = self.bot.guild_dict[ctx.guild.id]['trainers'].setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('settings', {}).setdefault('mute', False)
        start_time = self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['alerts']['settings'].setdefault('active_start', None)
        end_time = self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['alerts']['settings'].setdefault('active_end', None)
        user_link = self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['alerts']['settings'].setdefault('link', True)
        if mute:
            mute_str = f"Reply with **unmute** to unmute your DM alerts from Meowth"
        else:
            mute_str = f"Reply with **mute** to globally mute all DM alerts from Meowth"
        if user_link:
            link_str = f"Reply with **unlink** to unlink your **!want** list from your boss notifications. You are currently linked meaning your **!want** list controls all pokemon alerts. If you unlink, your **!want** list will be used for wild, research, and nest reports only and **!want boss <pokemon>** will be used for raid boss @mentions."
        else:
            link_str = f"Reply with **link** to link your **!want** list to your boss notifications. Your current **!want** list will be used for wild, research, raid @mentions, and nest reports."
        settings_embed = discord.Embed(description=f"", colour=ctx.me.colour)
        settings_embed.add_field(name=f"**{'unmute' if mute else 'mute'}**", value=f"{mute_str}", inline=False)
        settings_embed.add_field(name=f"**time**", value=f"Reply with **time** to set your active hours. Your start time setting will be when Meowth can start sending DMs each day and your end time setting will be when Meowth will stop sending DMs each day. If you set these to **none**, meowth will DM you regardless of time unless DMs are muted.", inline=False)
        settings_embed.add_field(name=f"**{'unlink' if user_link else 'link'}**", value=f"{link_str}", inline=False)
        settings_embed.add_field(name=f"**cancel**", value=f"Reply with **cancel** to stop changing settings.", inline=False)
        settings_embed.add_field(name="**Current Settings**", value=f"Muted: {mute}\nStart Time: {start_time.strftime('%I:%M %p') if start_time else 'None'}\nEnd Time: {end_time.strftime('%I:%M %p') if start_time else 'None'}\nLink: {user_link}", inline=False)
        settings_msg = await ctx.send(f"{ctx.author.mention} reply with one of the following options:", embed=settings_embed, delete_after=120)
        try:
            reply = await ctx.bot.wait_for('message', timeout=120, check=(lambda message: (message.author == ctx.author)))
        except asyncio.TimeoutError:
            await ctx.send(f"Meowth! You took to long to reply! Try the **{ctx.prefix}want settings** command again!", delete_after=120)
            return
        await utils.safe_delete(reply)
        if reply.content.lower() == "cancel":
            await ctx.send(f"{ctx.author.mention} - Your DM settings have not changed.")
            return
        elif reply.content.lower() == "mute":
            await ctx.send(f"{ctx.author.mention} - Your DM alerts are now muted.")
            self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['alerts']['settings']['mute'] = True
        elif reply.content.lower() == "unmute":
            await ctx.send(f"{ctx.author.mention} - Your DM alerts are now unmuted.")
            self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['alerts']['settings']['mute'] = False
        elif reply.content.lower() == "time":
            await ctx.send(f"Please enter the time you would like to **start receiving** DMs each day. *Ex: 8:00 AM*. You can reply with **none** to turn off active hours and receive all DMs regardless of time.", delete_after=120)
            try:
                time_reply = await ctx.bot.wait_for('message', timeout=120, check=(lambda message: (message.author == ctx.author and message.channel == ctx.channel)))
            except asyncio.TimeoutError:
                await ctx.send(f"Meowth! You took to long to reply! Try the **{ctx.prefix}want settings** command again!", delete_after=30)
                return
            await utils.safe_delete(time_reply)
            if time_reply.content.lower() == "none":
                await ctx.send(f"{ctx.author.mention} - You will now receive all DMs you are subscribed to, regardless of time.")
                self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['alerts']['settings']['active_start'] = None
                self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['alerts']['settings']['active_end'] = None
                return
            try:
                start_set = dateparser.parse(time_reply.content.lower())
            except ValueError:
                await ctx.send(f"Meowth! I couldn't understand your reply! Try the **{ctx.prefix}want settings** command again!", delete_after=30)
                return
            await ctx.send(f"Please enter the time you would like to **stop receiving** DMs each day. *Ex: 9:00 PM*", delete_after=120)
            try:
                time_reply = await ctx.bot.wait_for('message', timeout=120, check=(lambda message: (message.author == ctx.author and message.channel == ctx.channel)))
            except asyncio.TimeoutError:
                await ctx.send(f"Meowth! You took to long to reply! Try the **{ctx.prefix}want settings** command again!", delete_after=30)
                return
            await utils.safe_delete(time_reply)
            try:
                end_set = dateparser.parse(time_reply.content.lower())
            except ValueError:
                await ctx.send(f"Meowth! I couldn't understand your reply! Try the **{ctx.prefix}want settings** command again!", delete_after=30)
                return
            await ctx.send(f"{ctx.author.mention} - Your DM alerts will start at {start_set.time().strftime('%I:%M %p')} and stop at {end_set.time().strftime('%I:%M %p')} each day.")
            self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['alerts']['settings']['active_start'] = start_set.time()
            self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['alerts']['settings']['active_end'] = end_set.time()
        elif reply.content.lower() == "link":
            await ctx.send(f"{ctx.author.mention} - Your **!want** list controls all pokemon notifications.")
            self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['alerts']['settings']['link'] = True
        elif reply.content.lower() == "unlink":
            await ctx.send(f"{ctx.author.mention} - Your **!want** list controls everything but raid @mentions. Add raid @mentions through **!want boss <pokemon>**.")
            self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['alerts']['settings']['link'] = False
        else:
            await ctx.send(f"Meowth! I couldn't understand your reply! Try the **{ctx.prefix}want settings** command again!", delete_after=30)
        if reply.content.lower() == "link" or reply.content.lower() == "unlink":
            add_list = []
            remove_list = []
            if self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['alerts']['settings']['link']:
                user_wants = self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['alerts'].setdefault('wants', [])
            else:
                user_wants = self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['alerts'].setdefault('bosses', [])
            want_names = [utils.get_name(self.bot, x) for x in user_wants]
            want_names = [x.lower() for x in want_names]
            for role in ctx.author.roles:
                if role.name.lower() not in want_names and role.name.lower() in self.bot.pkmn_list:
                    remove_list.append(role)
            for want in want_names:
                if want in self.bot.raid_list:
                    role = discord.utils.get(ctx.guild.roles, name=want)
                    if role and role not in ctx.author.roles:
                        add_list.append(role)
            if remove_list:
                await ctx.author.remove_roles(*remove_list)
            if add_list:
                await ctx.author.add_roles(*add_list)

    @commands.group(case_insensitive=True, invoke_without_command=True)
    @checks.allowwant()
    async def unwant(self, ctx, *, pokemon):
        """Remove a Pokemon from your wanted list.

        Usage: !unwant <species>
        You will no longer be notified of reports about this Pokemon."""
        message = ctx.message
        guild = message.guild
        channel = message.channel
        user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('wants', [])
        user_link = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('settings', {}).setdefault('link', True)
        role_list = []
        unwant_list = []
        if ctx.invoked_subcommand == None:
            unwant_split = pokemon.lower().split(',')
            for entered_unwant in unwant_split:
                pokemon, match_list = await pkmn_class.Pokemon.ask_pokemon(ctx, entered_unwant.strip())
                if pokemon:
                    unwant_list.append(pokemon.name.lower())
                else:
                    return
            for entered_unwant in unwant_list:
                role = discord.utils.get(guild.roles, name=entered_unwant)
                if role in message.author.roles and user_link:
                    role_list.append(role)
                if utils.get_number(self.bot, entered_unwant) in user_wants:
                    user_wants.remove(utils.get_number(self.bot, entered_unwant))
            await message.author.remove_roles(*role_list)
            await message.add_reaction(self.bot.config['command_done'])

    @unwant.command(name='boss')
    @checks.allowwant()
    async def unwant_boss(self, ctx, *, bosses):
        """Remove a boss from your wanted list.

        Usage: !unwant boss <species>
        You will no longer be notified of reports about this Pokemon."""
        message = ctx.message
        guild = message.guild
        channel = message.channel
        user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('bosses', [])
        user_link = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('settings', {}).setdefault('link', True)
        role_list = []
        unwant_list = []
        unwant_split = bosses.lower().split(',')
        if user_link:
            await message.channel.send(f"{ctx.author.mention} - Your boss list is linked to your want list, please use **!unwant** to remove pokemon.")
            return
        for entered_unwant in unwant_split:
            pokemon, match_list = await pkmn_class.Pokemon.ask_pokemon(ctx, entered_unwant.strip())
            if pokemon:
                unwant_list.append(pokemon.name.lower())
            else:
                return
        for entered_unwant in unwant_list:
            role = discord.utils.get(guild.roles, name=entered_unwant)
            if role in message.author.roles:
                role_list.append(role)
            if utils.get_number(self.bot, entered_unwant) in user_wants:
                user_wants.remove(utils.get_number(self.bot, entered_unwant))
        await message.author.remove_roles(*role_list)
        await message.add_reaction(self.bot.config['command_done'])

    @unwant.command(name='all')
    @checks.allowwant()
    async def unwant_all(self, ctx):
        """Remove all things from your wanted list.

        Usage: !unwant all
        All wants are removed."""
        message = ctx.message
        guild = message.guild
        channel = message.channel
        author = message.author
        user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('wants', [])
        want_count = len(user_wants)
        user_bosses = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('bosses', [])
        boss_count = len(user_bosses)
        user_gyms = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('gyms', [])
        gym_count = len(user_gyms)
        user_stops = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('stops', [])
        stop_count = len(user_stops)
        user_items = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('items', [])
        item_count = len(user_items)
        user_types = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('types', [])
        type_count = len(user_types)
        user_ivs = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('ivs', [])
        iv_count = len(user_ivs)
        unwant_msg = ""
        count = want_count + boss_count + gym_count + stop_count + item_count + type_count + iv_count
        if count == 0:
            await channel.send(content=_('{0}, you have no pokemon, gyms, stops, types, IVs, or items in your want list.').format(author.mention), delete_after=10)
            return
        unwant_msg = f"{author.mention}"
        await channel.trigger_typing()
        if want_count > 0:
            roles = author.roles
            remove_roles = []
            for role in roles:
                if role.name in self.bot.pkmn_list:
                    remove_roles.append(role)
            await author.remove_roles(*remove_roles)
            self.bot.guild_dict[guild.id]['trainers'][message.author.id]['alerts']['wants'] = []
            unwant_msg += _(" I've removed {0} pokemon from your want list.").format(count)
        if gym_count > 0:
            self.bot.guild_dict[guild.id]['trainers'][message.author.id]['alerts']['gyms'] = []
            unwant_msg += _(" I've removed {0} gyms from your want list.").format(gym_count)
        if stop_count > 0:
            self.bot.guild_dict[guild.id]['trainers'][message.author.id]['alerts']['stops'] = []
            unwant_msg += _(" I've removed {0} stops from your want list.").format(stop_count)
        if item_count > 0:
            self.bot.guild_dict[guild.id]['trainers'][message.author.id]['alerts']['items'] = []
            unwant_msg += _(" I've removed {0} items from your want list.").format(item_count)
        if boss_count > 0:
            self.bot.guild_dict[guild.id]['trainers'][message.author.id]['alerts']['bosses'] = []
            unwant_msg += _(" I've removed {0} bosses from your want list.").format(boss_count)
        if type_count > 0:
            self.bot.guild_dict[guild.id]['trainers'][message.author.id]['alerts']['types'] = []
            unwant_msg += _(" I've removed {0} types from your want list.").format(type_count)
        if iv_count > 0:
            self.bot.guild_dict[guild.id]['trainers'][message.author.id]['alerts']['ivs'] = []
            unwant_msg += _(" I've removed {0} IVs from your want list.").format(iv_count)
        await channel.send(unwant_msg)

    @unwant.command(name='gym')
    @checks.allowwant()
    async def unwant_gym(self, ctx, *, gyms):
        """Remove a gym from your wanted list.

        Usage: !unwant gym <gym list>
        You will no longer be notified of reports about this gym."""
        message = ctx.message
        guild = message.guild
        channel = message.channel
        user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('gyms', [])
        unwant_list = []
        unwant_split = gyms.lower().split(',')
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        if not gym_matching_cog:
            return
        gyms = gym_matching_cog.get_gyms(ctx.guild.id)
        for entered_unwant in unwant_split:
            gym = await gym_matching_cog.poi_match_prompt(ctx, entered_unwant, gyms, None)
            if gym:
                unwant_list.append(gym.lower())
        for entered_unwant in unwant_list:
            if entered_unwant.lower() in user_wants:
                user_wants.remove(entered_unwant.lower())
        await message.add_reaction(self.bot.config['command_done'])

    @unwant.command(name='stop')
    @checks.allowwant()
    async def unwant_stop(self, ctx, *, stops):
        """Remove a pokestop from your wanted list.

        Usage: !unwant stop <stop list>
        You will no longer be notified of reports about this pokestop."""
        message = ctx.message
        guild = message.guild
        channel = message.channel
        user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('stops', [])
        unwant_list = []
        unwant_split = stops.lower().split(',')
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        if not gym_matching_cog:
            return
        stops = gym_matching_cog.get_stops(ctx.guild.id)
        for entered_unwant in unwant_split:
            stop = await gym_matching_cog.poi_match_prompt(ctx, entered_unwant, None, stops)
            if stop:
                unwant_list.append(stop.lower())
        for entered_unwant in unwant_list:
            if entered_unwant.lower() in user_wants:
                user_wants.remove(entered_unwant.lower())
        await message.add_reaction(self.bot.config['command_done'])

    @unwant.command(name='item')
    @checks.allowwant()
    async def unwant_item(self, ctx, *, items):
        """Remove a item from your wanted list.

        Usage: !unwant item <item list>
        You will no longer be notified of reports about this item."""
        message = ctx.message
        guild = message.guild
        channel = message.channel
        user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('items', [])
        item_list = ["incense", "poke ball", "great ball", "ultra ball", "master ball", "potion", "super potion", "hyper potion", "max potion", "revive", "max revive", "razz berry", "golden razz berry", "nanab berry", "pinap berry", "silver pinap berry", "fast tm", "charged tm", "rare candy", "lucky egg", "stardust", "lure module", "star piece", "premium raid pass", "egg incubator", "super incubator", "team medallion", "sun stone", "metal coat", "dragon scale", "up-grade", "sinnoh stone"]
        unwant_list = []
        unwant_split = items.lower().split(',')
        for entered_unwant in unwant_split:
            if entered_unwant in item_list:
                unwant_list.append(entered_unwant.lower())
        for entered_unwant in unwant_list:
            if entered_unwant.lower() in user_wants:
                user_wants.remove(entered_unwant.lower())
        await message.add_reaction(self.bot.config['command_done'])

    @unwant.command(name='type')
    @checks.allowwant()
    async def unwant_type(self, ctx, *, types):
        """Remove a type from your wanted list.

        Usage: !unwant type <species>
        You will no longer be notified of reports about this type."""
        message = ctx.message
        guild = message.guild
        channel = message.channel
        user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('types', [])
        type_list = ["normal", "fighting", "flying", "poison", "ground", "rock", "bug", "ghost", "steel", "fire", "water", "grass", "electric", "psychic", "ice", "dragon", "dark", "fairy"]
        unwant_list = []
        unwant_split = types.lower().split(',')
        for entered_unwant in unwant_split:
            if entered_unwant in type_list:
                unwant_list.append(entered_unwant.lower())
        for entered_unwant in unwant_list:
            if entered_unwant.lower() in user_wants:
                user_wants.remove(entered_unwant.lower())
        await message.add_reaction(self.bot.config['command_done'])

    @unwant.command(name='iv', aliases=['ivs'])
    @checks.allowwant()
    async def unwant_iv(self, ctx, *, ivs):
        """Remove a IV from your wanted list.

        Usage: !unwant iv <iv list>
        You will no longer be notified of reports about this IV."""
        message = ctx.message
        guild = message.guild
        channel = message.channel
        user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('ivs', [])
        unwant_list = []
        unwant_split = ivs.lower().split(',')
        for entered_unwant in unwant_split:
            if "+" in entered_unwant.lower():
                entered_unwant = entered_unwant.replace("+", "").strip()
                if not entered_unwant.strip().isdigit():
                    continue
                for iv in range(int(entered_unwant), 101):
                    if iv not in unwant_list:
                        unwant_list.append(str(iv))
            else:
                if not entered_unwant.strip().isdigit():
                    continue
                if entered_unwant not in unwant_list:
                    unwant_list.append(entered_unwant)
        for entered_unwant in unwant_list:
            if int(entered_unwant) in user_wants:
                user_wants.remove(int(entered_unwant))
        await message.add_reaction(self.bot.config['command_done'])

def setup(bot):
    bot.add_cog(Want(bot))
