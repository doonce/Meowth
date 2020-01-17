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
    async def want(self, ctx, *, pokemon=None):
        """Add a Pokemon to your wanted list. Currently used for wild, raid, research, invasion, nest reports.

        Usage: !want <species>
        Meowth will DM you if anyone reports something on your want list.
        Behind the scenes, Meowth tracks user !wants by storing information.
        Guided version available with just !want"""
        message = ctx.message
        author = message.author
        guild = message.guild
        channel = message.channel
        user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('wants', [])
        user_link = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('settings', {}).setdefault('link', True)
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        gym_matching_cog = self.bot.cogs.get("GymMatching")
        error = False
        want_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/ic_softbank.png?cache=1")
        want_embed.set_footer(text=_('Sent by @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        want_msg = f"Meowth! I'll help you add a new alert subscription!\n\nFirst, I'll need to know what **type** of alert you'd like to subscribe to. Reply with one of the following or reply with **cancel** to stop anytime."
        want_embed.add_field(name=_('**New Alert Subscription**'), value=want_msg, inline=False)
        want_embed.add_field(name=_('**Pokemon**'), value=f"Reply with **pokemon** to want specific pokemon for research, wild, {'nest, trade, and raid reports.' if user_link else 'and nest reports.'}", inline=False)
        role_list = self.bot.guild_dict[guild.id]['configure_dict'].get('want', {}).get('roles', [])
        if not user_link:
            want_embed.add_field(name=_('**Boss** / **Trade**'), value=f"Reply with **boss** to want specific pokemon for raid reports. Reply with **trade** to want specific pokemon for trade listings.", inline=False)
        gyms, stops = [], []
        if gym_matching_cog:
            gyms = gym_matching_cog.get_gyms(ctx.guild.id)
            stops = gym_matching_cog.get_stops(ctx.guild.id)
            want_embed.add_field(name=f"**{'Gym' if gyms else ''}{' / ' if gyms and stops else ''}{'Stop' if stops else ''}**", value=f"{'Reply with **gym** to want raids and eggs at specific gyms.' if gyms else ''} {'Reply with **stop** to want research and wild spawns at specific pokestops.' if stops else ''}", inline=False)
        if role_list:
            want_embed.add_field(name=_('**Role**'), value=f"Reply with **role** to subscribe to server roles.", inline=False)
        want_embed.add_field(name=_('**IV** / **Level** / **Egg**'), value=f"Reply with **iv** or **level** to want wild spawns of a specific IV / level. Reply with **egg** to want raid eggs of a specific level", inline=False)
        want_embed.add_field(name=_('**Type**'), value=f"Reply with **type** to want wild, research, and nest reports of a specific type.", inline=False)
        want_embed.add_field(name=_('**Item**'), value=f"Reply with **item** to want sspecific items from research.", inline=False)
        want_embed.add_field(name=_('**Settings**'), value=f"Reply with **settings** to access your want settings.", inline=False)
        want_embed.add_field(name=_('**List**'), value=f"Reply with **list** to view your want list.", inline=False)
        while True:
            async with ctx.typing():
                def check(reply):
                    if reply.author is not guild.me and reply.channel.id == channel.id and reply.author == message.author:
                        return True
                    else:
                        return False
                if pokemon:
                    if pokemon.split(',')[0].lower().strip() in self.bot.type_list:
                        return await ctx.invoke(self.bot.get_command('want type'), types=pokemon)
                    elif gym_matching_cog and pokemon.split(',')[0].lower().strip() in [x.lower() for x in gyms]:
                        return await ctx.invoke(self.bot.get_command('want gym'), gyms=pokemon)
                    elif gym_matching_cog and pokemon.split(',')[0].lower().strip() in [x.lower() for x in stops]:
                        return await ctx.invoke(self.bot.get_command('want stop'), stops=pokemon)
                    elif pokemon.split(',')[0].lower().strip() in self.bot.item_list:
                        return await ctx.invoke(self.bot.get_command('want item'), items=pokemon)
                    elif pokemon.split(',')[0].lower().strip() == "ex":
                        return await ctx.invoke(self.bot.get_command('want egg'), levels=pokemon)
                    elif pokemon.split(',')[0].lower().strip().isdigit() and int(pokemon.split(',')[0].lower().strip()) < 101:
                        want_embed.clear_fields()
                        want_embed.add_field(name=_('**New Alert Subscription**'), value=f"Meowth! You entered a number, which can be used for **IV**, **level**, **egg**, or **pokemon**. Which did you mean? Reply with your answer or with **cancel** to stop.", inline=False)
                        want_category_wait = await channel.send(embed=want_embed)
                        try:
                            want_category_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            want_category_msg = None
                        await utils.safe_delete(want_category_wait)
                        if not want_category_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(want_category_msg)
                        if want_category_msg.clean_content.lower() == "cancel":
                            error = _("cancelled the report")
                            break
                        elif want_category_msg.clean_content.lower() == "iv":
                            return await ctx.invoke(self.bot.get_command('want iv'), ivs=pokemon)
                        elif want_category_msg.clean_content.lower() == "level":
                            return await ctx.invoke(self.bot.get_command('want level'), levels=pokemon)
                        elif want_category_msg.clean_content.lower() == "pokemon":
                            return await self._want_pokemon(ctx, pokemon)
                        elif want_category_msg.clean_content.lower() == "egg":
                            return await ctx.invoke(self.bot.get_command('want egg'), levels=pokemon)
                        else:
                            continue
                    else:
                        return await self._want_pokemon(ctx, pokemon)
                else:
                    want_category_wait = await channel.send(embed=want_embed)
                    try:
                        want_category_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        want_category_msg = None
                    await utils.safe_delete(want_category_wait)
                    if not want_category_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(want_category_msg)
                    if want_category_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif want_category_msg.clean_content.lower() == "pokemon":
                        want_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/ic_grass.png?cache=1")
                        want_embed.clear_fields()
                        want_embed.add_field(name=_('**New Alert Subscription**'), value=f"Now, reply with a comma separated list of the pokemon you'd like to subscribe to. You can use any forms, genders, or sizes for specific control. Use **{ctx.prefix}pokedex <pokemon>** to see if there are gender or form differences available. You can reply with **cancel** to stop anytime.", inline=False)
                        want_wait = await channel.send(embed=want_embed)
                        try:
                            want_sub_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            want_sub_msg = None
                        await utils.safe_delete(want_wait)
                        if not want_sub_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(want_sub_msg)
                        if want_sub_msg.clean_content.lower() == "cancel":
                            error = _("cancelled your request")
                            break
                        elif want_sub_msg:
                            await self._want_pokemon(ctx, want_sub_msg.clean_content.lower())
                        break
                    elif want_category_msg.clean_content.lower() == "boss" and not user_link:
                        want_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/eggs/5.png?cache=1")
                        want_embed.clear_fields()
                        want_embed.add_field(name=_('**New Alert Subscription**'), value=f"Now, reply with a comma separated list of the pokemon you'd like to subscribe to. You can reply with **cancel** to stop anytime.", inline=False)
                        want_wait = await channel.send(embed=want_embed)
                        try:
                            want_sub_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            want_sub_msg = None
                        await utils.safe_delete(want_wait)
                        if not want_sub_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(want_sub_msg)
                        if want_sub_msg.clean_content.lower() == "cancel":
                            error = _("cancelled your request")
                            break
                        elif want_sub_msg:
                            ctx.message.content = want_sub_msg.clean_content
                            want_command = ctx.command.all_commands.get('boss')
                            if want_command:
                                return await ctx.invoke(want_command, bosses=ctx.message.content)
                        break
                    elif want_category_msg.clean_content.lower() == "trade" and not user_link and checks.check_tradeset(ctx):
                        want_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/trade_icon_small.png?cache=1")
                        want_embed.clear_fields()
                        want_embed.add_field(name=_('**New Alert Subscription**'), value=f"Now, reply with a comma separated list of the pokemon you'd like to subscribe to. You can reply with **cancel** to stop anytime.", inline=False)
                        want_wait = await channel.send(embed=want_embed)
                        try:
                            want_sub_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            want_sub_msg = None
                        await utils.safe_delete(want_wait)
                        if not want_sub_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(want_sub_msg)
                        if want_sub_msg.clean_content.lower() == "cancel":
                            error = _("cancelled your request")
                            break
                        elif want_sub_msg:
                            ctx.message.content = want_sub_msg.clean_content
                            want_command = ctx.command.all_commands.get('trade')
                            if want_command:
                                return await ctx.invoke(want_command, trades=ctx.message.content)
                        break
                    elif want_category_msg.clean_content.lower() == "gym" and gym_matching_cog and gyms:
                        want_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/gym-arena.png?cache=1")
                        want_embed.clear_fields()
                        want_embed.add_field(name=_('**New Alert Subscription**'), value=f"Now, reply with a comma separated list of the gyms you'd like to subscribe to. You can reply with **cancel** to stop anytime.", inline=False)
                        want_wait = await channel.send(embed=want_embed)
                        try:
                            want_sub_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            want_sub_msg = None
                        await utils.safe_delete(want_wait)
                        if not want_sub_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(want_sub_msg)
                        if want_sub_msg.clean_content.lower() == "cancel":
                            error = _("cancelled your request")
                            break
                        elif want_sub_msg:
                            ctx.message.content = want_sub_msg.clean_content
                            want_command = ctx.command.all_commands.get('gym')
                            if want_command:
                                return await ctx.invoke(want_command, gyms=ctx.message.content)
                        break
                    elif want_category_msg.clean_content.lower() == "stop" and gym_matching_cog and stops:
                        want_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/pokestop_near.png?cache=1")
                        want_embed.clear_fields()
                        want_embed.add_field(name=_('**New Alert Subscription**'), value=f"Now, reply with a comma separated list of the pokestops you'd like to subscribe to. You can reply with **cancel** to stop anytime.", inline=False)
                        want_wait = await channel.send(embed=want_embed)
                        try:
                            want_sub_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            want_sub_msg = None
                        await utils.safe_delete(want_wait)
                        if not want_sub_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(want_sub_msg)
                        if want_sub_msg.clean_content.lower() == "cancel":
                            error = _("cancelled your request")
                            break
                        elif want_sub_msg:
                            ctx.message.content = want_sub_msg.clean_content
                            want_command = ctx.command.all_commands.get('stop')
                            if want_command:
                                return await ctx.invoke(want_command, stops=ctx.message.content)
                        break
                    elif want_category_msg.clean_content.lower() == "iv":
                        want_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/trade_tut_strength_adjust.png?cache=1")
                        want_embed.clear_fields()
                        want_embed.add_field(name=_('**New Alert Subscription**'), value=f"Now, reply with a comma separated list of the IVs you'd like to subscribe to or IV+ to subscribe to that IV through 100. You can reply with **cancel** to stop anytime.", inline=False)
                        want_wait = await channel.send(embed=want_embed)
                        try:
                            want_sub_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            want_sub_msg = None
                        await utils.safe_delete(want_wait)
                        if not want_sub_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(want_sub_msg)
                        if want_sub_msg.clean_content.lower() == "cancel":
                            error = _("cancelled your request")
                            break
                        elif want_sub_msg:
                            ctx.message.content = want_sub_msg.clean_content
                            want_command = ctx.command.all_commands.get('iv')
                            if want_command:
                                return await ctx.invoke(want_command, ivs=ctx.message.content)
                        break
                    elif want_category_msg.clean_content.lower() == "level":
                        want_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/trade_tut_strength_adjust.png?cache=1")
                        want_embed.clear_fields()
                        want_embed.add_field(name=_('**New Alert Subscription**'), value=f"Now, reply with a comma separated list of the levels you'd like to subscribe to or level+ to subscribe to that level through 40. You can reply with **cancel** to stop anytime.", inline=False)
                        want_wait = await channel.send(embed=want_embed)
                        try:
                            want_sub_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            want_sub_msg = None
                        await utils.safe_delete(want_wait)
                        if not want_sub_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(want_sub_msg)
                        if want_sub_msg.clean_content.lower() == "cancel":
                            error = _("cancelled your request")
                            break
                        elif want_sub_msg:
                            ctx.message.content = want_sub_msg.clean_content
                            want_command = ctx.command.all_commands.get('level')
                            if want_command:
                                return await ctx.invoke(want_command, levels=ctx.message.content)
                        break
                    elif want_category_msg.clean_content.lower() == "egg":
                        want_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/eggs/5.png?cache=1")
                        want_embed.clear_fields()
                        want_embed.add_field(name=_('**New Alert Subscription**'), value=f"Now, reply with a comma separated list of the raid eggs you'd like to subscribe to. You can reply with **cancel** to stop anytime.", inline=False)
                        want_wait = await channel.send(embed=want_embed)
                        try:
                            want_sub_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            want_sub_msg = None
                        await utils.safe_delete(want_wait)
                        if not want_sub_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(want_sub_msg)
                        if want_sub_msg.clean_content.lower() == "cancel":
                            error = _("cancelled your request")
                            break
                        elif want_sub_msg:
                            ctx.message.content = want_sub_msg.clean_content
                            want_command = ctx.command.all_commands.get('egg')
                            if want_command:
                                return await ctx.invoke(want_command, levels=ctx.message.content)
                        break
                    elif want_category_msg.clean_content.lower() == "item":
                        want_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/MysteryItem.png?cache=1")
                        want_embed.clear_fields()
                        want_embed.add_field(name=_('**New Alert Subscription**'), value=f"Now, reply with a comma separated list of the items you'd like to subscribe to.\n\nSupported items include: {', '.join(self.bot.item_list)}.\n\nYou can reply with **cancel** to stop anytime.", inline=False)
                        want_wait = await channel.send(embed=want_embed)
                        try:
                            want_sub_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            want_sub_msg = None
                        await utils.safe_delete(want_wait)
                        if not want_sub_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(want_sub_msg)
                        if want_sub_msg.clean_content.lower() == "cancel":
                            error = _("cancelled your request")
                            break
                        elif want_sub_msg:
                            ctx.message.content = want_sub_msg.clean_content
                            want_command = ctx.command.all_commands.get('item')
                            if want_command:
                                return await ctx.invoke(want_command, items=ctx.message.content)
                        break
                    elif want_category_msg.clean_content.lower() == "type":
                        want_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/types.png?cache=1")
                        want_embed.clear_fields()
                        want_embed.add_field(name=_('**New Alert Subscription**'), value=f"Now, reply with a comma separated list of the types you'd like to subscribe to.\n\nSupported types include: {', '.join(self.bot.type_list)}.\n\nYou can reply with **cancel** to stop anytime.", inline=False)
                        want_wait = await channel.send(embed=want_embed)
                        try:
                            want_sub_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            want_sub_msg = None
                        await utils.safe_delete(want_wait)
                        if not want_sub_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(want_sub_msg)
                        if want_sub_msg.clean_content.lower() == "cancel":
                            error = _("cancelled your request")
                            break
                        elif want_sub_msg:
                            ctx.message.content = want_sub_msg.clean_content
                            want_command = ctx.command.all_commands.get('type')
                            if want_command:
                                return await ctx.invoke(want_command, types=ctx.message.content)
                        break
                    elif want_category_msg.clean_content.lower() == "role" and role_list:
                        want_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/discord.png?cache=1")
                        want_embed.clear_fields()
                        role_list = [guild.get_role(x) for x in role_list]
                        role_list = [x.mention for x in role_list]
                        want_embed.add_field(name=_('**New Alert Subscription**'), value=f"Now, reply with a comma separated list of the roles you'd like to subscribe to.\n\nSupported roles include:{(', ').join(role_list)}.\n\nYou can reply with **cancel** to stop anytime.", inline=False)
                        want_wait = await channel.send(embed=want_embed)
                        try:
                            want_sub_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            want_sub_msg = None
                        await utils.safe_delete(want_wait)
                        if not want_sub_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(want_sub_msg)
                        if want_sub_msg.clean_content.lower() == "cancel":
                            error = _("cancelled your request")
                            break
                        elif want_sub_msg:
                            ctx.message.content = want_sub_msg.clean_content
                            want_command = ctx.command.all_commands.get('role')
                            if want_command:
                                return await ctx.invoke(want_command, roles=ctx.message.content)
                        break
                    elif want_category_msg.clean_content.lower() == "settings":
                        want_command = ctx.command.all_commands.get('settings')
                        if want_command:
                            return await want_command.invoke(ctx)
                    elif want_category_msg.clean_content.lower() == "list":
                        await utils.safe_delete(ctx.message)
                        list_command = self.bot.get_command("list")
                        want_command = list_command.all_commands.get('wants')
                        return await want_command.invoke(ctx)
                    else:
                        error = _("entered something invalid")
                        break
        if error:
            want_embed.clear_fields()
            want_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/ic_softbank.png?cache=1")
            want_embed.add_field(name=_('**New Subscription Cancelled**'), value=_("Meowth! Your request has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await channel.send(embed=want_embed, delete_after=10)
            await utils.safe_delete(message)
            return

    @want.command(name="pokemon", hidden=True)
    @checks.allowwant()
    async def want_pokemon(self, ctx, *, pokemon):
        await self._want_pokemon(ctx, pokemon)

    async def _want_pokemon(self, ctx, pokemon):
        await ctx.trigger_typing()
        message = ctx.message
        author = message.author
        guild = message.guild
        channel = message.channel
        user_link = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('settings', {}).setdefault('link', True)
        want_split = pokemon.lower().split(',')
        want_list = []
        added_count = 0
        spellcheck_dict = {}
        spellcheck_list = []
        already_want_count = 0
        already_want_list = []
        added_list = []
        trade_warn = []
        want_embed = discord.Embed(colour=ctx.me.colour)
        if "boss" in ctx.invoked_with:
            user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('bosses', [])
            user_forms = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('boss_forms', [])
            want_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/eggs/5.png?cache=1")
            if user_link:
                return await message.channel.send(f"{ctx.author.mention} - Your boss list is linked to your want list, please use **!want** to add pokemon.")
        elif "trade" in ctx.invoked_with:
            user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('trades', [])
            user_forms = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('trade_forms', [])
            if user_link:
                return await message.channel.send(f"{ctx.author.mention} - Your trade want list is linked to your want list, please use **!want** to add pokemon.")
        else:
            user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('wants', [])
            user_forms = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('forms', [])
            want_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/ic_grass.png?cache=1")
        for entered_want in want_split:
            if entered_want.lower() in self.bot.form_dict['list'] and not entered_want.isdigit():
                forms = []
                for pokemon in self.bot.form_dict:
                    if pokemon == "list" or pokemon == "two_words":
                        continue
                    if self.bot.form_dict[pokemon].get(entered_want.lower()):
                        forms.append(f"{entered_want} {utils.get_name(self.bot, pokemon)}")
                forms = [await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, x) for x in forms]
                want_list.extend([x for x in forms if x])
                continue
            pokemon = await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, entered_want.strip(), allow_digits=True)
            if str(pokemon) == "XS Rattata":
                sizes = [await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, x) for x in ["Alolan XS Rattata", "Male XS Rattata", "Female XS Rattata", "XS Rattata"]]
                want_list.extend(sizes)
                continue
            if str(pokemon) == "XL Magikarp":
                sizes = [await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, x) for x in ["Male XL Magikarp", "Female XL Magikarp", "XL Magikarp"]]
                want_list.extend(sizes)
                continue
            if pokemon:
                if (pokemon.shiny or pokemon.shadow == "purified") and "trade" not in ctx.invoked_with:
                    if not checks.check_tradeset(ctx):
                        pokemon.shiny = False
                        pokemon.shadow = False
                    else:
                        trade_warn.append(str(pokemon))
                want_list.append(pokemon)
            elif len(want_split) == 1 and "list" in entered_want:
                await utils.safe_delete(ctx.message)
                return await ctx.invoke(self.bot.get_command('list wants'))
            else:
                spellcheck_list.append(entered_want)
                match, score = utils.get_match(ctx.bot.pkmn_list, entered_want)
                spellcheck_dict[entered_want] = match
        for entered_want in want_list:
            boss_str = ""
            if entered_want.id in self.bot.raid_list and (user_link or "boss" in ctx.invoked_with):
                boss_str = f" (Level {entered_want.raid_level} Boss)"
            if (entered_want.size or entered_want.gender or entered_want.region or entered_want.form or entered_want.shiny or entered_want.shadow) and len(str(entered_want).split()) > 1:
                if str(entered_want) in user_forms:
                    already_want_list.append(str(entered_want))
                    already_want_count += 1
                else:
                    user_forms.append(str(entered_want))
                    added_list.append(f"{str(entered_want)}{boss_str}")
                    added_count += 1
            else:
                if entered_want.id in user_wants:
                    already_want_list.append(entered_want.name.title())
                    already_want_count += 1
                else:
                    user_wants.append(entered_want.id)
                    added_list.append(f"{entered_want.name.title()}{boss_str}")
                    added_count += 1
        want_count = added_count + already_want_count + len(spellcheck_dict)
        confirmation_msg = f"Meowth! {ctx.author.display_name}, out of your total **{want_count}** {'boss' if 'boss' in ctx.invoked_with else 'pokemon'}{'es' if want_count > 1 and 'boss' in ctx.invoked_with else ''}:\n\n"
        if added_count > 0:
            confirmation_msg += _('**{added_count} Added:** \n\t{added_list}\n').format(added_count=added_count, added_list=', '.join(added_list))
        if already_want_count > 0:
            confirmation_msg += _('**{already_want_count} Already Wanted:** \n\t{already_want_list}\n').format(already_want_count=already_want_count, already_want_list=', '.join(already_want_list))
        if spellcheck_dict:
            spellcheckmsg = ''
            for word in spellcheck_dict:
                spellcheckmsg += _('\n\t{word}').format(word=word)
                if spellcheck_dict[word]:
                    spellcheckmsg += _(': *({correction}?)*').format(correction=spellcheck_dict[word])
            confirmation_msg += _('**{count} Not Valid:**').format(count=len(spellcheck_dict)) + spellcheckmsg
        if len(added_list) == 1:
            pokemon = await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, added_list[0])
            want_embed.set_thumbnail(url=pokemon.img_url)
        want_embed.add_field(name=_('**New Alert Subscription**'), value=confirmation_msg, inline=False)
        want_confirmation = await channel.send(embed=want_embed)
        if trade_warn:
            await ctx.send(f"Meowth! {ctx.author.mention}, just so you know, **{(', ').join(trade_warn)}** will only be alerted through new trade listings.", delete_after=30)

    @want.command(name='boss', aliases=['bosses'])
    @checks.allowwant()
    async def want_boss(self, ctx, *, bosses):
        """Adds a boss to your wants. Currently used for raid reports.

        Usage: !want boss <boss list>"""
        await ctx.invoke(self.bot.get_command('want pokemon'), pokemon=bosses)

    @want.command(name='trade', aliases=['trades'])
    @checks.allowwant()
    async def want_trades(self, ctx, *, trades):
        """Adds a trade listing to your wants for alerts if wanted pokemon is listed.

        Usage: !want trade <trade list>"""
        if not checks.check_tradeset(ctx):
            return await ctx.send(f"Meowth! Trading isn't enabled on this server!", delete_after=30)
        await ctx.invoke(self.bot.get_command('want pokemon'), pokemon=trades)

    async def _want_poi(self, ctx, pois, poi_type="gym"):
        await ctx.trigger_typing()
        message = ctx.message
        guild = message.guild
        channel = message.channel
        want_split = pois.lower().split(',')
        want_list = []
        added_count = 0
        spellcheck_dict = {}
        spellcheck_list = []
        already_want_count = 0
        already_want_list = []
        added_list = []
        want_embed = discord.Embed(colour=ctx.me.colour)
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        if not gym_matching_cog:
            return
        if poi_type == "stop":
            pois = gym_matching_cog.get_stops(ctx.guild.id)
            user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('stops', [])
            want_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/pokestop_near.png?cache=1")
        else:
            pois = gym_matching_cog.get_gyms(ctx.guild.id)
            user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('gyms', [])
            want_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/gym-arena.png?cache=1")
        for entered_want in want_split:
            gym = await gym_matching_cog.poi_match_prompt(ctx, entered_want, pois, None)
            if gym:
                want_list.append(gym.lower())
            else:
                spellcheck_list.append(entered_want)
                match, score = utils.get_match(pois.keys(), entered_want)
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
        confirmation_msg = f"Meowth! {ctx.author.display_name}, out of your total **{want_count}** {'stop' if poi_type == 'stop' else 'gym'}{'s' if want_count > 1 else ''}:\n\n"
        if added_count > 0:
            confirmation_msg += _('**{added_count} Added:** \n\t{added_list}\n').format(added_count=added_count, added_list=', '.join(added_list))
        if already_want_count > 0:
            confirmation_msg += _('**{already_want_count} Already Wanted:** \n\t{already_want_list}\n').format(already_want_count=already_want_count, already_want_list=', '.join(already_want_list))
        if spellcheck_dict:
            spellcheckmsg = ''
            for word in spellcheck_dict:
                spellcheckmsg += _('\n\t{word}').format(word=word)
                if spellcheck_dict[word]:
                    spellcheckmsg += _(': *({correction}?)*').format(correction=spellcheck_dict[word])
            confirmation_msg += _('**{count} Not Valid:**').format(count=len(spellcheck_dict)) + spellcheckmsg
        want_embed.add_field(name=_('**New Alert Subscription**'), value=confirmation_msg, inline=False)
        want_confirmation = await channel.send(embed=want_embed)

    @want.command(name='gym', aliases=['gyms'])
    @checks.allowwant()
    async def want_gym(self, ctx, *, gyms):
        """Add a gym to your want list. Currently used for raid and raid egg reports.

        Usage: !want gym <gym list>"""
        await self._want_poi(ctx, gyms, poi_type="gym")

    @want.command(name='exraid')
    @checks.allowwant()
    async def want_exraid(self, ctx):
        """Add all EX eligible gyms to your want list. Currently used for raid and raid egg reports.

        Usage: !want exraid"""
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        ex_list = []
        if not gym_matching_cog:
            return
        gyms = gym_matching_cog.get_gyms(ctx.guild.id)
        for gym in gyms:
            if "ex" in gyms[gym].get('notes', '').lower():
                if gyms[gym].get('alias'):
                    gym = gyms[gym].get('alias')
                if gym not in ex_list:
                    ex_list.append(gym)
        await self._want_poi(ctx, (', ').join(ex_list), poi_type="gym")

    @want.command(name='stop', aliases=['pokestop', 'pokestops', 'stops'])
    @checks.allowwant()
    async def want_stop(self, ctx, *, stops):
        """Add a pokestop to your want list. Currently used for wild, invasion, lure, and research reports.

        Usage: !want stop <stop list>"""
        await self._want_poi(ctx, stops, poi_type="stop")

    @want.command(name='item', aliases=['items'])
    @checks.allowwant()
    async def want_item(self, ctx, *, items):
        """Add a item to your want list. Currently used research and lure reports.

        Item List = incense, poke ball, great ball, ultra ball, master ball, potion, super potion, hyper potion, max potion, revive, max revive, razz berry, golden razz berry, nanab berry, pinap berry, silver pinap berry, fast tm, charged tm, rare candy, lucky egg, stardust, lure module, glacial lure module, magnetic lure module, mossy lure module, star piece, premium raid pass, egg incubator, super incubator, team medallion, sun stone, metal coat, dragon scale, up-grade, sinnoh stone, unova stone, mysterious component, rocket radar

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
        want_embed = discord.Embed(colour=ctx.me.colour).set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/MysteryItem.png?cache=1")
        user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('items', [])
        for entered_want in want_split:
            if entered_want.strip().lower() in self.bot.item_list:
                want_list.append(entered_want.strip().lower())
            else:
                match = await utils.autocorrect(self.bot, entered_want, self.bot.item_list, ctx.channel, ctx.author)
                if match:
                    want_list.append(match.lower())
                else:
                    spellcheck_list.append(entered_want)
                    match, score = utils.get_match(self.bot.item_list, entered_want)
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
        confirmation_msg = _('Meowth! {member}, out of your total **{count}** item{s}:\n\n').format(member=ctx.author.display_name, count=want_count, s="s" if want_count > 1 else "")
        if added_count > 0:
            confirmation_msg += _('**{added_count} Added:** \n\t{added_list}\n').format(added_count=added_count, added_list=', '.join(added_list))
        if already_want_count > 0:
            confirmation_msg += _('**{already_want_count} Already Wanted:** \n\t{already_want_list}\n').format(already_want_count=already_want_count, already_want_list=', '.join(already_want_list))
        if spellcheck_dict:
            spellcheckmsg = ''
            for word in spellcheck_dict:
                spellcheckmsg += _('\n\t{word}').format(word=word)
                if spellcheck_dict[word]:
                    spellcheckmsg += _(': *({correction}?)*').format(correction=spellcheck_dict[word])
            confirmation_msg += _('**{count} Not Valid:**').format(count=len(spellcheck_dict)) + spellcheckmsg
        if len(added_list) == 1:
            thumbnail_url, item = await utils.get_item(added_list[0])
            want_embed.set_thumbnail(url=thumbnail_url)
        want_embed.add_field(name=_('**New Alert Subscription**'), value=confirmation_msg, inline=False)
        want_confirmation = await channel.send(embed=want_embed)

    @want.command(name='type', aliases=['types'])
    @checks.allowwant()
    async def want_type(self, ctx, *, types):
        """Add a pokemon type to your want list. Currently used for wild, research, invasion, and nest reports.

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
        want_embed = discord.Embed(colour=ctx.me.colour).set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/types.png?cache=1")
        user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('types', [])
        for entered_want in want_split:
            if entered_want.strip().lower() in self.bot.type_list:
                want_list.append(entered_want.strip().lower())
            else:
                match = await utils.autocorrect(self.bot, entered_want, self.bot.type_list, ctx.channel, ctx.author)
                if match:
                    want_list.append(match.lower())
                else:
                    spellcheck_list.append(entered_want)
                    match, score = utils.get_match(self.bot.type_list, entered_want)
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
        confirmation_msg = _('Meowth! {member}, out of your total **{count}** type{s}:\n\n').format(member=ctx.author.display_name, count=want_count, s="s" if want_count > 1 else "")
        if added_count > 0:
            confirmation_msg += _('**{added_count} Added:** \n\t{added_list}\n').format(added_count=added_count, added_list=', '.join(added_list))
        if already_want_count > 0:
            confirmation_msg += _('**{already_want_count} Already Wanted:** \n\t{already_want_list}\n').format(already_want_count=already_want_count, already_want_list=', '.join(already_want_list))
        if spellcheck_dict:
            spellcheckmsg = ''
            for word in spellcheck_dict:
                spellcheckmsg += _('\n\t{word}').format(word=word)
                if spellcheck_dict[word]:
                    spellcheckmsg += _(': *({correction}?)*').format(correction=spellcheck_dict[word])
            confirmation_msg += _('**{count} Not Valid:**').format(count=len(spellcheck_dict)) + spellcheckmsg
        if len(added_list) == 1:
            want_embed.set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/emoji/{added_list[0].lower()}.png")
        want_embed.add_field(name=_('**New Alert Subscription**'), value=confirmation_msg, inline=False)
        want_confirmation = await channel.send(embed=want_embed)

    @want.command(name='iv', aliases=['ivs'])
    @checks.allowwant()
    async def want_iv(self, ctx, *, ivs):
        """Add a IV to your want list. Currently used for wild reports.

        Usage: !want iv <iv list>
        Enter individual numbers, a range with iv-iv, or iv+ to add iv to 100"""
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
        want_embed = discord.Embed(colour=ctx.me.colour).set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/trade_tut_strength_adjust.png?cache=1")
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
            elif "-" in entered_want.lower():
                range_split = entered_want.split("-")
                if range_split[0].isdigit() and range_split[1].isdigit() and int(range_split[1]) > int(range_split[0]) and int(range_split[1]) <= 100:
                    for iv in range(int(range_split[0]), int(range_split[1])+1):
                        want_list.append(str(iv))
                else:
                    error_list.append(entered_want)
            else:
                if not entered_want.strip().isdigit() or int(entered_want.strip()) > 100:
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
        confirmation_msg = _('Meowth! {member}, out of your total **{count}** iv{s}:\n\n').format(member=ctx.author.display_name, count=want_count, s="s" if want_count > 1 else "")
        if added_count > 0:
            confirmation_msg += _('**{added_count} Added:** \n\t{added_list}\n').format(added_count=added_count, added_list=', '.join(added_list))
        if already_want_count > 0:
            confirmation_msg += _('**{already_want_count} Already Wanted:** \n\t{already_want_list}\n').format(already_want_count=already_want_count, already_want_list=', '.join(already_want_list))
        if error_list:
            error_msg = ''
            for word in error_list:
                error_msg += _('\n\t{word}').format(word=word)
            confirmation_msg += _('\n**{count} Not Valid:**').format(count=len(error_list)) + error_msg
        want_embed.add_field(name=_('**New Alert Subscription**'), value=confirmation_msg, inline=False)
        want_confirmation = await channel.send(embed=want_embed)

    @want.command(name='level', aliases=['levels'])
    @checks.allowwant()
    async def want_level(self, ctx, *, levels):
        """Add a level to your want list. Currently used for wild reports.

        Usage: !want level <level list>
        Enter individual numbers, a range with level-level, or level+ to add level to 40"""
        await ctx.trigger_typing()
        message = ctx.message
        guild = message.guild
        channel = message.channel
        want_split = levels.lower().split(',')
        want_list = []
        added_count = 0
        already_want_count = 0
        already_want_list = []
        added_list = []
        error_list = []
        want_embed = discord.Embed(colour=ctx.me.colour).set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/trade_tut_strength_adjust.png?cache=1")
        user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('levels', [])
        for entered_want in want_split:
            if "+" in entered_want.lower():
                entered_want = entered_want.replace("+", "").strip()
                if not entered_want.strip().isdigit():
                    error_list.append(entered_want)
                    continue
                for level in range(int(entered_want), 41):
                    if level not in want_list:
                        want_list.append(str(level))
            elif "-" in entered_want.lower():
                range_split = entered_want.split("-")
                if range_split[0].isdigit() and range_split[1].isdigit() and int(range_split[1]) > int(range_split[0]) and int(range_split[1]) <= 40:
                    for level in range(int(range_split[0]), int(range_split[1])+1):
                        want_list.append(str(level))
                else:
                    error_list.append(entered_want)
            else:
                if not entered_want.strip().isdigit() or int(entered_want.strip()) > 40:
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
        confirmation_msg = _('Meowth! {member}, out of your total **{count}** level{s}:\n\n').format(member=ctx.author.display_name, count=want_count, s="s" if want_count > 1 else "")
        if added_count > 0:
            confirmation_msg += _('**{added_count} Added:** \n\t{added_list}\n').format(added_count=added_count, added_list=', '.join(added_list))
        if already_want_count > 0:
            confirmation_msg += _('**{already_want_count} Already Wanted:** \n\t{already_want_list}\n').format(already_want_count=already_want_count, already_want_list=', '.join(already_want_list))
        if error_list:
            error_msg = ''
            for word in error_list:
                error_msg += _('\n\t{word}').format(word=word)
            confirmation_msg += _('\n**{count} Not Valid:**').format(count=len(error_list)) + error_msg
        want_embed.add_field(name=_('**New Alert Subscription**'), value=confirmation_msg, inline=False)
        want_confirmation = await channel.send(embed=want_embed)

    @want.command(name='egg', aliases=["eggs", "raidegg", "raideggs"])
    @checks.allowwant()
    async def want_raidegg(self, ctx, *, levels):
        """Add raid egg levels to subscription list.

        Usage: !want egg <1 to 5 or EX>"""
        await ctx.trigger_typing()
        message = ctx.message
        guild = message.guild
        channel = message.channel
        want_split = levels.lower().split(',')
        want_list = []
        added_count = 0
        already_want_count = 0
        already_want_list = []
        added_list = []
        error_list = []
        want_embed = discord.Embed(colour=ctx.me.colour).set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/eggs/5.png?cache=1")
        user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('raid_eggs', [])
        for entered_want in want_split:
            if entered_want.isdigit() and int(entered_want.strip()) > 5:
                error_list.append(entered_want)
                continue
            if not entered_want.strip().isdigit() and entered_want.lower() != "ex":
                error_list.append(entered_want)
                continue
            if entered_want not in want_list:
                want_list.append(entered_want.upper())
        for entered_want in want_list:
            if entered_want in user_wants:
                already_want_list.append(entered_want)
                already_want_count += 1
            else:
                user_wants.append(entered_want)
                added_list.append(f"{entered_want}")
                added_count += 1
        want_count = added_count + already_want_count + len(error_list)
        confirmation_msg = _('Meowth! {member}, out of your total **{count}** raid egg{s}:\n\n').format(member=ctx.author.display_name, count=want_count, s="s" if want_count > 1 else "")
        if added_count > 0:
            confirmation_msg += _('**{added_count} Added:** \n\t{added_list}\n').format(added_count=added_count, added_list=', '.join(added_list))
        if already_want_count > 0:
            confirmation_msg += _('**{already_want_count} Already Wanted:** \n\t{already_want_list}\n').format(already_want_count=already_want_count, already_want_list=', '.join(already_want_list))
        if error_list:
            error_msg = ''
            for word in error_list:
                error_msg += _('\n\t{word}').format(word=word)
            confirmation_msg += _('\n**{count} Not Valid:**').format(count=len(error_list)) + error_msg
        want_embed.add_field(name=_('**New Alert Subscription**'), value=confirmation_msg, inline=False)
        want_confirmation = await channel.send(embed=want_embed)

    @want.command(name='role', aliases=['roles'])
    @checks.allowwant()
    async def want_role(self, ctx, *, roles):
        """Adds a joinable role to your wants.

        Usage: !want role <role list>"""
        await ctx.trigger_typing()
        message = ctx.message
        guild = message.guild
        channel = message.channel
        want_split = roles.lower().split(',')
        want_list = []
        added_count = 0
        spellcheck_dict = {}
        already_want_count = 0
        already_want_list = []
        added_list = []
        role_list = []
        want_embed = discord.Embed(colour=ctx.me.colour).set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/discord.png?cache=1")
        converter = commands.RoleConverter()
        join_roles = [guild.get_role(x) for x in self.bot.guild_dict[guild.id]['configure_dict'].get('want', {}).get('roles', [])]
        for entered_want in want_split:
            try:
                role = await converter.convert(ctx, entered_want)
            except:
                role = None
            if role:
                want_list.append(role)
            else:
                match, score = utils.get_match([x.name for x in ctx.guild.roles], entered_want)
                spellcheck_dict[entered_want] = match
        for role in want_list:
            role_str = ""
            if role in join_roles:
                role_str = f" ({role.mention})"
                if role not in ctx.author.roles:
                    role_list.append(role)
                    added_list.append(f"{role.name}{role_str}")
                    added_count += 1
                else:
                    already_want_list.append(f"{role.name}{role_str}")
                    already_want_count += 1
            else:
                spellcheck_dict[role.name] = None
        await ctx.author.add_roles(*role_list)
        want_count = added_count + already_want_count + len(spellcheck_dict)
        confirmation_msg = _('Meowth! {member}, out of your total **{count}** role{s}:\n\n').format(member=ctx.author.display_name, count=want_count, s="es" if want_count > 1 else "")
        if added_count > 0:
            confirmation_msg += _('**{added_count} Added:** \n\t{added_list}\n').format(added_count=added_count, added_list=', '.join(added_list))
        if already_want_count > 0:
            confirmation_msg += _('**{already_want_count} Already Wanted:** \n\t{already_want_list}\n').format(already_want_count=already_want_count, already_want_list=', '.join(already_want_list))
        if spellcheck_dict:
            spellcheckmsg = ''
            for word in spellcheck_dict:
                spellcheckmsg += _('\n\t{word}').format(word=word)
                if spellcheck_dict[word]:
                    spellcheckmsg += _(': *({correction}?)*').format(correction=spellcheck_dict[word])
            confirmation_msg += _('**{count} Not Valid:**').format(count=len(spellcheck_dict)) + spellcheckmsg
        want_embed.add_field(name=_('**New Alert Subscription**'), value=confirmation_msg, inline=False)
        want_confirmation = await channel.send(embed=want_embed)

    @want.command()
    @checks.allowwant()
    async def settings(self, ctx):
        """Changes alert settings such as muting and active hours.

        Usage: !want settings"""
        await ctx.trigger_typing()
        user_mute = self.bot.guild_dict[ctx.guild.id]['trainers'].setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('settings', {}).setdefault('mute', {"raid":False, "invasion":False, "lure":False, "wild":False, "research":False, "nest":False, "trade":False})
        mute_options = ["raid", "invasion", "lure", "wild", "research", "nest", "trade"]
        start_time = self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['alerts']['settings'].setdefault('active_start', None)
        end_time = self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['alerts']['settings'].setdefault('active_end', None)
        user_link = self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['alerts']['settings'].setdefault('link', True)
        if user_link:
            link_str = f"Reply with **unlink** to unlink your **!want** list from your boss notifications. You are currently linked meaning your **!want** list controls all pokemon alerts. If you unlink, your **!want** list will be used for wild, research, and nest reports only. **!want boss <pokemon>** will be used for raid boss @mentions and **!want trade <pokemon>** will be used for trade wants."
        else:
            link_str = f"Reply with **link** to link your **!want** list to your boss notifications. Your current **!want** list will be used for wild, research, raid @mentions, and nest reports."
        settings_embed = discord.Embed(description=f"", colour=ctx.me.colour)
        settings_embed.add_field(name=f"**mute**", value=f"Reply with **mute** to select DM alerts from Meowth to mute. You will be able to choose `None`, `All`, or any report type combination of {(', ').join(mute_options)}. This will mute all DMs of selected types. To have finer control, try **categories**", inline=False)
        settings_embed.add_field(name=f"**time**", value=f"Reply with **time** to set your active hours. Your start time setting will be when Meowth can start sending DMs each day and your end time setting will be when Meowth will stop sending DMs each day. If you set these to **none**, meowth will DM you regardless of time unless DMs are muted.", inline=False)
        settings_embed.add_field(name=f"**{'unlink' if user_link else 'link'}**", value=f"{link_str}", inline=False)
        settings_embed.add_field(name=f"**categories**", value=f"Reply with **categories** to set your alert categories. For example, if you want a certain pokestop but only want wild alerts but no lures or invasions, use this setting.", inline=False)
        settings_embed.add_field(name=f"**cancel**", value=f"Reply with **cancel** to stop changing settings.", inline=False)
        settings_embed.add_field(name="**Current Settings**", value=f"DMs Muted: {(', ').join([x for x in user_mute.keys() if user_mute[x]])}{'None' if not any(user_mute.values()) else ''}\nStart Time: {start_time.strftime('%I:%M %p') if start_time else 'None'}\nEnd Time: {end_time.strftime('%I:%M %p') if start_time else 'None'}\nLink: {user_link}", inline=False)
        settings_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/ic_softbank.png?cache=1")
        settings_msg = await ctx.send(f"{ctx.author.mention} reply with one of the following options:", embed=settings_embed, delete_after=120)
        def check(reply):
            if reply.author is not ctx.guild.me and reply.channel.id == ctx.channel.id and reply.author == ctx.message.author:
                return True
            else:
                return False
        try:
            reply = await ctx.bot.wait_for('message', timeout=120, check=check)
        except asyncio.TimeoutError:
            return await ctx.send(f"Meowth! You took to long to reply! Try the **{ctx.prefix}want settings** command again!", delete_after=120)
        await utils.safe_delete(reply)
        if reply.content.lower() == "cancel":
            return await ctx.send(f"{ctx.author.mention} - Your DM settings have not changed.")

        elif "mute" in reply.content.lower():
            await ctx.send(f"Please enter the **report types** that you would like to mute. Choose from **{(', ').join(mute_options)}, all, none**", delete_after=120)
            try:
                mute_reply = await ctx.bot.wait_for('message', timeout=120, check=(lambda message: (message.author == ctx.author and message.channel == ctx.channel)))
            except asyncio.TimeoutError:
                return await ctx.send(f"Meowth! You took to long to reply! Try the **{ctx.prefix}want settings** command again!", delete_after=30)
            await utils.safe_delete(mute_reply)
            if mute_reply.content.lower() == "all":
                reply_list = mute_options
            elif mute_reply.content.lower() == "none":
                reply_list = []
            else:
                reply_list = mute_reply.content.lower().split(',')
                reply_list = [x.strip() for x in reply_list]
                reply_list = [x for x in reply_list if x in mute_options]
                if not reply_list:
                    return await ctx.send(f"Meowth! I couldn't understand your reply! Try the **{ctx.prefix}want settings** command again!", delete_after=30)
            user_setting = {}
            disable_list = set(mute_options) - set(reply_list)
            enable_list = set(mute_options) - set(disable_list)
            for item in disable_list:
                user_setting[item] = False
            for item in enable_list:
                user_setting[item] = True
            await ctx.send(f"{ctx.author.mention} - Your DM alert mute settings are set. DMs muted: {(', ').join([x for x in user_setting.keys() if user_setting[x]])}{'None' if not any(user_setting.values()) else ''}")
            self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['alerts']['settings']['mute'] = user_setting
        elif reply.content.lower() == "time":
            await ctx.send(f"Please enter the time you would like to **start receiving** DMs each day. *Ex: 8:00 AM*. You can reply with **none** to turn off active hours and receive all DMs regardless of time.", delete_after=120)
            try:
                time_reply = await ctx.bot.wait_for('message', timeout=120, check=(lambda message: (message.author == ctx.author and message.channel == ctx.channel)))
            except asyncio.TimeoutError:
                return await ctx.send(f"Meowth! You took to long to reply! Try the **{ctx.prefix}want settings** command again!", delete_after=30)
            await utils.safe_delete(time_reply)
            if time_reply.content.lower() == "none":
                await ctx.send(f"{ctx.author.mention} - You will now receive all DMs you are subscribed to, regardless of time.")
                self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['alerts']['settings']['active_start'] = None
                self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['alerts']['settings']['active_end'] = None
                return
            try:
                start_set = dateparser.parse(time_reply.content.lower())
            except ValueError:
                return await ctx.send(f"Meowth! I couldn't understand your reply! Try the **{ctx.prefix}want settings** command again!", delete_after=30)
            await ctx.send(f"Please enter the time you would like to **stop receiving** DMs each day. *Ex: 9:00 PM*", delete_after=120)
            try:
                time_reply = await ctx.bot.wait_for('message', timeout=120, check=(lambda message: (message.author == ctx.author and message.channel == ctx.channel)))
            except asyncio.TimeoutError:
                return await ctx.send(f"Meowth! You took to long to reply! Try the **{ctx.prefix}want settings** command again!", delete_after=30)
            await utils.safe_delete(time_reply)
            try:
                end_set = dateparser.parse(time_reply.content.lower())
            except ValueError:
                return await ctx.send(f"Meowth! I couldn't understand your reply! Try the **{ctx.prefix}want settings** command again!", delete_after=30)
            await ctx.send(f"{ctx.author.mention} - Your DM alerts will start at {start_set.time().strftime('%I:%M %p')} and stop at {end_set.time().strftime('%I:%M %p')} each day.")
            self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['alerts']['settings']['active_start'] = start_set.time()
            self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['alerts']['settings']['active_end'] = end_set.time()
        elif reply.content.lower() == "categories":
            return await ctx.invoke(self.bot.get_command("want categories"))
        elif reply.content.lower() == "link":
            await ctx.send(f"{ctx.author.mention} - Your **!want** list controls all pokemon notifications.")
            self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['alerts']['settings']['link'] = True
        elif reply.content.lower() == "unlink":
            await ctx.send(f"{ctx.author.mention} - Your **!want** list controls everything but raid @mentions. Add raid @mentions through **!want boss <pokemon>**.")
            self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['alerts']['settings']['link'] = False
        else:
            await ctx.send(f"Meowth! I couldn't understand your reply! Try the **{ctx.prefix}want settings** command again!", delete_after=30)
            await utils.safe_delete(settings_msg)

    @want.command(hidden=True)
    @checks.allowwant()
    async def categories(self, ctx):
        """Changes your want category (pokemon, type, item, etc.) preferences per report type (research, wild, invasion, etc.).

        Usage: !want categories"""
        categories = self.bot.guild_dict[ctx.guild.id]['trainers'].setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('settings', {}).setdefault('categories', {})
        category_list = ["pokemon", "pokestop", "item", "type"]
        pokemon_options = ["wild", "research", "invasion", "nest", "trade", "raid"]
        pokestop_options = ["research", "wild", "lure", "invasion"]
        type_options = ["wild", "research", "nest", "invasion", "trade", "raid"]
        item_options = ["research", "lure"]
        gym_options = ["raid"]
        raidegg_options = ["raid"]
        pokemon_settings = categories.get('pokemon', {})
        if not pokemon_settings:
            pokemon_settings = {k:True for k in pokemon_options}
        pokestop_settings = categories.get('stop', {})
        if not pokestop_settings:
            pokestop_settings = {k:True for k in pokestop_options}
        item_settings = categories.get('item', {})
        if not item_settings:
            item_settings = {k:True for k in item_options}
        type_settings = categories.get('type', {})
        if not type_settings:
            type_settings = {k:True for k in type_options}
        user_setting = {}
        settings_embed = discord.Embed(description=f"If your desired want list category isn't listed, that list is exclusive to one alert type. Use **{ctx.prefix}want** or **{ctx.prefix}unwant** to control that alert type. Raid bosses are controlled through your **{ctx.prefix}want settings** Link.", colour=ctx.me.colour)
        settings_embed.add_field(name=f"**pokemon**", value=f"Reply with **pokemon** to set which alert types will use your wanted pokemon list. Currently: {(', ').join([x for x in pokemon_options if pokemon_settings.get(x)])}", inline=False)
        settings_embed.add_field(name=f"**pokestop**", value=f"Reply with **pokestop** to set which alert types will use your wanted pokestop list. Currently: {(', ').join([x for x in pokestop_options if pokestop_settings.get(x)])}", inline=False)
        settings_embed.add_field(name=f"**item**", value=f"Reply with **item** to set which alert types will use your wanted item list. Currently: {(', ').join([x for x in item_options if item_settings.get(x)])}", inline=False)
        settings_embed.add_field(name=f"**type**", value=f"Reply with **type** to set which alert types will use your wanted type list. Currently: {(', ').join([x for x in type_options if type_settings.get(x)])}", inline=False)
        settings_embed.add_field(name=f"**reset**", value=f"Reply with **reset** to reset all alerts to default.", inline=False)
        settings_embed.add_field(name=f"**cancel**", value=f"Reply with **cancel** to stop changing settings.", inline=False)
        settings_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/ic_softbank.png?cache=1")
        settings_msg = await ctx.send(f"{ctx.author.mention} reply with one of the following options:", embed=settings_embed, delete_after=120)
        try:
            cat_reply = await ctx.bot.wait_for('message', timeout=120, check=(lambda message: (message.author == ctx.author and message.channel == ctx.channel)))
        except asyncio.TimeoutError:
            return await ctx.send(f"Meowth! You took to long to reply! Try the **{ctx.prefix}want settings** command again!", delete_after=30)
        await utils.safe_bulk_delete(ctx.channel, [cat_reply, settings_msg, ctx.message])
        if cat_reply.content.lower() in category_list:
            if cat_reply.content.lower() == "pokemon":
                settings_msg = await ctx.send(f"{ctx.author.mention} reply with the alert types you would like to receive **pokemon** alerts for. Any not listed will be disabled. List from the following options: **{(', ').join(pokemon_options)}** or reply with **all** to enable all.", delete_after=120)
                try:
                    cat_reply = await ctx.bot.wait_for('message', timeout=120, check=(lambda message: (message.author == ctx.author and message.channel == ctx.channel)))
                except asyncio.TimeoutError:
                    return await ctx.send(f"Meowth! You took to long to reply! Try the **{ctx.prefix}want settings** command again!", delete_after=30)
                if cat_reply.content.lower() == "all":
                    cat_reply.content = (', ').join(pokemon_options)
                elif cat_reply.content.lower() == "cancel":
                    return await ctx.send(f"{ctx.author.mention} - Your DM settings have not changed")
                reply_list = cat_reply.content.lower().split(',')
                reply_list = [x.strip() for x in reply_list]
                reply_list = [x for x in reply_list if x in pokemon_options]
                disable_list = set(pokemon_options) - set(reply_list)
                enable_list = set(pokemon_options) - set(disable_list)
                for item in disable_list:
                    user_setting[item] = False
                for item in enable_list:
                    user_setting[item] = True
                self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['alerts']['settings']['categories']['pokemon'] = user_setting
                await utils.safe_bulk_delete(ctx.channel, [cat_reply, settings_msg, ctx.message])
                await ctx.send(f"{ctx.author.mention} - Your DM settings for **pokemon** have been set to **{(', ').join(enable_list)}**.", delete_after=30)
            elif cat_reply.content.lower() == "pokestop":
                settings_msg = await ctx.send(f"{ctx.author.mention} reply with the alert types you would like to receive **pokestop** alerts for. Any not listed will be disabled. List from the following options: **{(', ').join(pokestop_options)}** or reply with **all** to enable all.", delete_after=120)
                try:
                    cat_reply = await ctx.bot.wait_for('message', timeout=120, check=(lambda message: (message.author == ctx.author and message.channel == ctx.channel)))
                except asyncio.TimeoutError:
                    return await ctx.send(f"Meowth! You took to long to reply! Try the **{ctx.prefix}want settings** command again!", delete_after=30)
                if cat_reply.content.lower() == "all":
                    cat_reply.content = (', ').join(pokestop_options)
                elif cat_reply.content.lower() == "cancel":
                    return await ctx.send(f"{ctx.author.mention} - Your DM settings have not changed")
                reply_list = cat_reply.content.lower().split(',')
                reply_list = [x.strip() for x in reply_list]
                reply_list = [x for x in reply_list if x in pokestop_options]
                disable_list = set(pokestop_options) - set(reply_list)
                enable_list = set(pokestop_options) - set(disable_list)
                for item in disable_list:
                    user_setting[item] = False
                for item in enable_list:
                    user_setting[item] = True
                self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['alerts']['settings']['categories']['pokestop'] = user_setting
                await utils.safe_bulk_delete(ctx.channel, [cat_reply, settings_msg, ctx.message])
                await ctx.send(f"{ctx.author.mention} - Your DM settings for **pokestop** have been set to **{(', ').join(enable_list)}**.", delete_after=30)
            elif cat_reply.content.lower() == "item":
                settings_msg = await ctx.send(f"{ctx.author.mention} reply with the alert types you would like to receive **item** alerts for. Any not listed will be disabled. List from the following options: **{(', ').join(item_options)}** or reply with **all** to enable all.", delete_after=120)
                try:
                    cat_reply = await ctx.bot.wait_for('message', timeout=120, check=(lambda message: (message.author == ctx.author and message.channel == ctx.channel)))
                except asyncio.TimeoutError:
                    return await ctx.send(f"Meowth! You took to long to reply! Try the **{ctx.prefix}want settings** command again!", delete_after=30)
                if cat_reply.content.lower() == "all":
                    cat_reply.content = (', ').join(item_options)
                elif cat_reply.content.lower() == "cancel":
                    return await ctx.send(f"{ctx.author.mention} - Your DM settings have not changed")
                reply_list = cat_reply.content.lower().split(',')
                reply_list = [x.strip() for x in reply_list]
                reply_list = [x for x in reply_list if x in item_options]
                disable_list = set(item_options) - set(reply_list)
                enable_list = set(item_options) - set(disable_list)
                for item in disable_list:
                    user_setting[item] = False
                for item in enable_list:
                    user_setting[item] = True
                self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['alerts']['settings']['categories']['item'] = user_setting
                await utils.safe_bulk_delete(ctx.channel, [cat_reply, settings_msg, ctx.message])
                await ctx.send(f"{ctx.author.mention} - Your DM settings for **item** have been set to **{(', ').join(enable_list)}**.", delete_after=30)
            elif cat_reply.content.lower() == "type":
                settings_msg = await ctx.send(f"{ctx.author.mention} reply with the alert types you would like to receive **type** alerts for. Any not listed will be disabled. List from the following options: **{(', ').join(type_options)}** or reply with **all** to enable all.", delete_after=120)
                try:
                    cat_reply = await ctx.bot.wait_for('message', timeout=120, check=(lambda message: (message.author == ctx.author and message.channel == ctx.channel)))
                except asyncio.TimeoutError:
                    return await ctx.send(f"Meowth! You took to long to reply! Try the **{ctx.prefix}want settings** command again!", delete_after=30)
                if cat_reply.content.lower() == "all":
                    cat_reply.content = (', ').join(type_options)
                elif cat_reply.content.lower() == "cancel":
                    return await ctx.send(f"{ctx.author.mention} - Your DM settings have not changed")
                reply_list = cat_reply.content.lower().split(',')
                reply_list = [x.strip() for x in reply_list]
                reply_list = [x for x in reply_list if x in type_options]
                disable_list = set(type_options) - set(reply_list)
                enable_list = set(type_options) - set(disable_list)
                for item in disable_list:
                    user_setting[item] = False
                for item in enable_list:
                    user_setting[item] = True
                self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['alerts']['settings']['categories']['type'] = user_setting
                await utils.safe_bulk_delete(ctx.channel, [cat_reply, settings_msg, ctx.message])
                await ctx.send(f"{ctx.author.mention} - Your DM settings for **type** have been set to **{(', ').join(enable_list)}**.", delete_after=30)
            else:
                await ctx.send(f"{ctx.author.mention} - Your DM settings have not changed.", delete_after=30)
        elif cat_reply.content.lower() == "reset":
            self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['alerts']['settings']['categories'] = {}
            await ctx.send(f"{ctx.author.mention} - Your DM settings for all categories has been reset.", delete_after=30)
        else:
            await ctx.send(f"{ctx.author.mention} - Your DM settings have not changed.", delete_after=30)

    @commands.group(case_insensitive=True, invoke_without_command=True)
    @checks.allowwant()
    async def unwant(self, ctx, *, pokemon=""):
        """Remove a subscription from your wanted list.

        Usage: !unwant [pokemon]
        You will no longer be notified of reports about this Pokemon.
        Guided version available with just !unwant"""
        message = ctx.message
        author = message.author
        guild = message.guild
        channel = message.channel
        user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('wants', [])
        user_link = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('settings', {}).setdefault('link', True)
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        gym_matching_cog = self.bot.cogs.get("GymMatching")
        error = False
        user_wants = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('wants', [])
        user_wants = sorted(user_wants)
        wantlist = [utils.get_name(self.bot, x).title() for x in user_wants]
        user_forms = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('forms', [])
        user_bosses = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('bosses', [])
        user_bossforms = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('boss_forms', [])
        user_trades = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('trades', [])
        user_tradeforms = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('trade_forms', [])
        user_bosses = sorted(user_bosses)
        bosslist = [utils.get_name(self.bot, x).title() for x in user_bosses]
        user_gyms = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('gyms', [])
        user_gyms = [x.title() for x in user_gyms]
        user_stops = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('stops', [])
        user_stops = [x.title() for x in user_stops]
        user_ivs = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('ivs', [])
        user_ivs = sorted(user_ivs)
        user_ivs = [str(x) for x in user_ivs]
        user_levels = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('levels', [])
        user_levels = sorted(user_levels)
        user_levels = [str(x) for x in user_levels]
        user_items = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('items', [])
        user_items = [x.title() for x in user_items]
        user_types = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('types', [])
        user_types = [x.title() for x in user_types]
        user_eggs = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('raid_eggs', [])
        user_eggs = [x.title() for x in user_eggs]
        join_roles = [guild.get_role(x) for x in self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('want', {}).get('roles', [])]
        user_roles = [x for x in ctx.author.roles if x in join_roles]
        want_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/ic_softbank.png?cache=1")
        want_embed.set_footer(text=_('Sent by @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        want_msg = f"Meowth! I'll help you remove an alert subscription!\n\nFirst, I'll need to know what **type** of alert you'd like to unsubscribe from. Reply with one of the following or reply with **cancel** to stop anytime."
        want_embed.add_field(name=_('**Remove Alert Subscription**'), value=want_msg, inline=False)
        if not any([user_wants, user_bosses, user_gyms, user_stops, user_ivs, user_levels, user_items, user_types, user_forms, user_roles, user_eggs]):
            want_embed.clear_fields()
            want_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/ic_softbank.png?cache=1")
            want_embed.add_field(name=_('**Alert Unsubscription Cancelled**'), value=_("Meowth! Your request has been cancelled because you don't have any subscriptions! Add some with **!want**.").format(error=error), inline=False)
            confirmation = await channel.send(embed=want_embed, delete_after=10)
            await utils.safe_delete(message)
            return
        if user_wants:
            want_embed.add_field(name=_('**Pokemon**'), value=f"Reply with **pokemon** to unwant specific pokemon for research, wild, {'nest, trade, and raid reports.' if user_link else 'and nest reports.'}", inline=False)
        if not user_link and (user_bosses or user_bossforms or user_trades or user_tradeforms):
            want_embed.add_field(name=_('**Boss** / **Trade**'), value=f"Reply with **boss** to unwant specific pokemon for raid reports. Reply with **trade** to unwant specific pokemon for trade listings.", inline=False)
        gyms, stops = [], []
        if gym_matching_cog:
            gyms = gym_matching_cog.get_gyms(ctx.guild.id)
            stops = gym_matching_cog.get_stops(ctx.guild.id)
            if user_gyms or user_stops:
                want_embed.add_field(name=f"**{'Gym' if gyms and user_gyms else ''}{' / ' if gyms and user_gyms and stops and user_stops else ''}{'Stop' if stops and user_stops else ''}**", value=f"{'Reply with **gym** to unwant raids and eggs at specific gyms.' if gyms else ''} {'Reply with **stop** to unwant research and wild spawns at specific pokestops.' if stops else ''}", inline=False)
        if user_roles:
            want_embed.add_field(name=_('**Role**'), value=f"Reply with **role** to unwant server roles.", inline=False)
        if user_ivs:
            want_embed.add_field(name=_('**IV**'), value=f"Reply with **iv** to unwant wild spawns of a specific IV.", inline=False)
        if user_levels:
            want_embed.add_field(name=_('**Level**'), value=f"Reply with **level** to unwant wild spawns of a specific level.", inline=False)
        if user_eggs:
            want_embed.add_field(name=_('**Egg**'), value=f"Reply with **level** to unwant raid eggs of a specific level.", inline=False)
        if user_types:
            want_embed.add_field(name=_('**Type**'), value=f"Reply with **type** to unwant wild, research, and nest reports of a specific type.", inline=False)
        if user_items:
            want_embed.add_field(name=_('**Item**'), value=f"Reply with **item** to unwant sspecific items from research.", inline=False)
        want_embed.add_field(name=_('**All**'), value=f"Reply with **all** to unwant everything.", inline=False)
        while True:
            async with ctx.typing():
                def check(reply):
                    if reply.author is not guild.me and reply.channel.id == channel.id and reply.author == message.author:
                        return True
                    else:
                        return False
                if pokemon:
                    if pokemon.split(',')[0].lower().strip() in self.bot.type_list:
                        return await ctx.invoke(self.bot.get_command('unwant type'), types=pokemon)
                    elif gym_matching_cog and pokemon.split(',')[0].lower().strip() in [x.lower() for x in gyms]:
                        return await ctx.invoke(self.bot.get_command('unwant gym'), gyms=pokemon)
                    elif gym_matching_cog and pokemon.split(',')[0].lower().strip() in [x.lower() for x in stops]:
                        return await ctx.invoke(self.bot.get_command('unwant stop'), stops=pokemon)
                    elif pokemon.split(',')[0].lower().strip() in self.bot.item_list:
                        return await ctx.invoke(self.bot.get_command('unwant item'), items=pokemon)
                    elif pokemon.split(',')[0].lower().strip() == "ex":
                        return await ctx.invoke(self.bot.get_command('unwant egg'), levels=pokemon)
                    elif pokemon.split(',')[0].lower().strip().isdigit() and int(pokemon.split(',')[0].lower().strip()) < 101:
                        want_embed.clear_fields()
                        want_embed.add_field(name=_('**Remove Alert Subscription**'), value=f"Meowth! You entered a number, which can be used for **IV**, **level**, **egg**, or **pokemon**. Which did you mean? Reply with your answer or with **cancel** to stop.", inline=False)
                        want_category_wait = await channel.send(embed=want_embed)
                        try:
                            want_category_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            want_category_msg = None
                        await utils.safe_delete(want_category_wait)
                        if not want_category_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(want_category_msg)
                        if want_category_msg.clean_content.lower() == "cancel":
                            error = _("cancelled the report")
                            break
                        elif want_category_msg.clean_content.lower() == "iv":
                            return await ctx.invoke(self.bot.get_command('unwant iv'), ivs=pokemon)
                        elif want_category_msg.clean_content.lower() == "level":
                            return await ctx.invoke(self.bot.get_command('unwant level'), levels=pokemon)
                        elif want_category_msg.clean_content.lower() == "egg":
                            return await ctx.invoke(self.bot.get_command('unwant egg'), levels=pokemon)
                        elif want_category_msg.clean_content.lower() == "pokemon":
                            return await self._unwant_pokemon(ctx, pokemon)
                        else:
                            continue
                    else:
                        return await self._unwant_pokemon(ctx, pokemon)
                else:
                    want_category_wait = await channel.send(embed=want_embed)
                    try:
                        want_category_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        want_category_msg = None
                    await utils.safe_delete(want_category_wait)
                    if not want_category_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(want_category_msg)
                    if want_category_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif want_category_msg.clean_content.lower() == "pokemon":
                        if not wantlist and not user_forms:
                            error = _("don't have wants of that type")
                            break
                        want_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/ic_grass.png?cache=1")
                        want_embed.clear_fields()
                        want_embed.add_field(name=_('**Remove Alert Subscription**'), value=f"Now, reply with a comma separated list of the pokemon you'd like to unsubscribe from.\n\nYour current want list is: {(', ').join(wantlist+user_forms)}\n\nYou can reply with **cancel** to stop anytime.", inline=False)
                        want_wait = await channel.send(embed=want_embed)
                        try:
                            want_sub_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            want_sub_msg = None
                        await utils.safe_delete(want_wait)
                        if not want_sub_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(want_sub_msg)
                        if want_sub_msg.clean_content.lower() == "cancel":
                            error = _("cancelled your request")
                            break
                        elif want_sub_msg:
                            await self._unwant_pokemon(ctx, want_sub_msg.clean_content.lower())
                        break
                    elif want_category_msg.clean_content.lower() == "boss" and not user_link:
                        if not bosslist:
                            error = _("don't have wants of that type")
                            break
                        want_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/eggs/5.png?cache=1")
                        want_embed.clear_fields()
                        want_embed.add_field(name=_('**Remove Alert Subscription**'), value=f"Now, reply with a comma separated list of the pokemon you'd like to unsubscribe from.\n\nYour current want list is: {(', ').join(bosslist+user_bossforms)}\n\nYou can reply with **cancel** to stop anytime.", inline=False)
                        want_wait = await channel.send(embed=want_embed)
                        try:
                            want_sub_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            want_sub_msg = None
                        await utils.safe_delete(want_wait)
                        if not want_sub_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(want_sub_msg)
                        if want_sub_msg.clean_content.lower() == "cancel":
                            error = _("cancelled your request")
                            break
                        elif want_sub_msg:
                            ctx.message.content = want_sub_msg.clean_content
                            want_command = ctx.command.all_commands.get('boss')
                            if want_command:
                                return await ctx.invoke(want_command, bosses=ctx.message.content)
                        break
                    elif want_category_msg.clean_content.lower() == "trade" and not user_link and checks.check_tradeset(ctx):
                        if not bosslist:
                            error = _("don't have wants of that type")
                            break
                        want_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/trade_icon_small.png?cache=1")
                        want_embed.clear_fields()
                        want_embed.add_field(name=_('**Remove Alert Subscription**'), value=f"Now, reply with a comma separated list of the pokemon you'd like to unsubscribe from.\n\nYour current want list is: {(', ').join(user_trades+user_tradeforms)}\n\nYou can reply with **cancel** to stop anytime.", inline=False)
                        want_wait = await channel.send(embed=want_embed)
                        try:
                            want_sub_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            want_sub_msg = None
                        await utils.safe_delete(want_wait)
                        if not want_sub_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(want_sub_msg)
                        if want_sub_msg.clean_content.lower() == "cancel":
                            error = _("cancelled your request")
                            break
                        elif want_sub_msg:
                            ctx.message.content = want_sub_msg.clean_content
                            want_command = ctx.command.all_commands.get('boss')
                            if want_command:
                                return await ctx.invoke(want_command, bosses=ctx.message.content)
                        break
                    elif want_category_msg.clean_content.lower() == "gym" and gym_matching_cog:
                        if not user_gyms:
                            error = _("don't have wants of that type")
                            break
                        want_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/gym-arena.png?cache=1")
                        want_embed.clear_fields()
                        want_embed.add_field(name=_('**Remove Alert Subscription**'), value=f"Now, reply with a comma separated list of the gyms you'd like to unsubscribe from.\n\nYour current want list is: {(', ').join(user_gyms)}\n\nYou can reply with **cancel** to stop anytime.", inline=False)
                        want_wait = await channel.send(embed=want_embed)
                        try:
                            want_sub_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            want_sub_msg = None
                        await utils.safe_delete(want_wait)
                        if not want_sub_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(want_sub_msg)
                        if want_sub_msg.clean_content.lower() == "cancel":
                            error = _("cancelled your request")
                            break
                        elif want_sub_msg:
                            ctx.message.content = want_sub_msg.clean_content
                            want_command = ctx.command.all_commands.get('gym')
                            if want_command:
                                return await ctx.invoke(want_command, gyms=ctx.message.content)
                        break
                    elif want_category_msg.clean_content.lower() == "stop" and gym_matching_cog:
                        if not user_stops:
                            error = _("don't have wants of that type")
                            break
                        want_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/pokestop_near.png?cache=1")
                        want_embed.clear_fields()
                        want_embed.add_field(name=_('**Remove Alert Subscription**'), value=f"Now, reply with a comma separated list of the pokestops you'd like to unsubscribe from.\n\nYour current want list is: {(', ').join(user_stops)}\n\nYou can reply with **cancel** to stop anytime.", inline=False)
                        want_wait = await channel.send(embed=want_embed)
                        try:
                            want_sub_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            want_sub_msg = None
                        await utils.safe_delete(want_wait)
                        if not want_sub_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(want_sub_msg)
                        if want_sub_msg.clean_content.lower() == "cancel":
                            error = _("cancelled your request")
                            break
                        elif want_sub_msg:
                            ctx.message.content = want_sub_msg.clean_content
                            want_command = ctx.command.all_commands.get('stop')
                            if want_command:
                                return await ctx.invoke(want_command, stops=ctx.message.content)
                        break
                    elif want_category_msg.clean_content.lower() == "iv":
                        if not user_ivs:
                            error = _("don't have wants of that type")
                            break
                        want_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/trade_tut_strength_adjust.png?cache=1")
                        want_embed.clear_fields()
                        want_embed.add_field(name=_('**Remove Alert Subscription**'), value=f"Now, reply with a comma separated list of the IVs you'd like to unsubscribe from or IV+ to unsubscribe from that IV through 100.\n\nYour current want list is: {(', ').join(user_ivs)}\n\nYou can reply with **cancel** to stop anytime.", inline=False)
                        want_wait = await channel.send(embed=want_embed)
                        try:
                            want_sub_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            want_sub_msg = None
                        await utils.safe_delete(want_wait)
                        if not want_sub_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(want_sub_msg)
                        if want_sub_msg.clean_content.lower() == "cancel":
                            error = _("cancelled your request")
                            break
                        elif want_sub_msg:
                            ctx.message.content = want_sub_msg.clean_content
                            want_command = ctx.command.all_commands.get('iv')
                            if want_command:
                                return await ctx.invoke(want_command, ivs=ctx.message.content)
                        break
                    elif want_category_msg.clean_content.lower() == "level":
                        if not user_levels:
                            error = _("don't have wants of that type")
                            break
                        want_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/trade_tut_strength_adjust.png?cache=1")
                        want_embed.clear_fields()
                        want_embed.add_field(name=_('**Remove Alert Subscription**'), value=f"Now, reply with a comma separated list of the levels you'd like to unsubscribe from or level+ to unsubscribe from that level through 40.\n\nYour current want list is: {(', ').join(user_levels)}\n\nYou can reply with **cancel** to stop anytime.", inline=False)
                        want_wait = await channel.send(embed=want_embed)
                        try:
                            want_sub_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            want_sub_msg = None
                        await utils.safe_delete(want_wait)
                        if not want_sub_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(want_sub_msg)
                        if want_sub_msg.clean_content.lower() == "cancel":
                            error = _("cancelled your request")
                            break
                        elif want_sub_msg:
                            ctx.message.content = want_sub_msg.clean_content
                            want_command = ctx.command.all_commands.get('level')
                            if want_command:
                                return await ctx.invoke(want_command, levels=ctx.message.content)
                        break
                    elif want_category_msg.clean_content.lower() == "egg":
                        if not user_eggs:
                            error = _("don't have wants of that type")
                            break
                        want_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/eggs/5.png?cache=1")
                        want_embed.clear_fields()
                        want_embed.add_field(name=_('**Remove Alert Subscription**'), value=f"Now, reply with a comma separated list of the raid eggs you'd like to unsubscribe from.\n\nYour current want list is: {(', ').join(user_eggs)}\n\nYou can reply with **cancel** to stop anytime.", inline=False)
                        want_wait = await channel.send(embed=want_embed)
                        try:
                            want_sub_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            want_sub_msg = None
                        await utils.safe_delete(want_wait)
                        if not want_sub_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(want_sub_msg)
                        if want_sub_msg.clean_content.lower() == "cancel":
                            error = _("cancelled your request")
                            break
                        elif want_sub_msg:
                            ctx.message.content = want_sub_msg.clean_content
                            want_command = ctx.command.all_commands.get('egg')
                            if want_command:
                                return await ctx.invoke(want_command, levels=ctx.message.content)
                        break
                    elif want_category_msg.clean_content.lower() == "item":
                        if not user_items:
                            error = _("don't have wants of that type")
                            break
                        want_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/MysteryItem.png?cache=1")
                        want_embed.clear_fields()
                        want_embed.add_field(name=_('**Remove Alert Subscription**'), value=f"Now, reply with a comma separated list of the items you'd like to unsubscribe from.\n\nYour current want list is: {(', ').join(user_items)}\n\nYou can reply with **cancel** to stop anytime.", inline=False)
                        want_wait = await channel.send(embed=want_embed)
                        try:
                            want_sub_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            want_sub_msg = None
                        await utils.safe_delete(want_wait)
                        if not want_sub_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(want_sub_msg)
                        if want_sub_msg.clean_content.lower() == "cancel":
                            error = _("cancelled your request")
                            break
                        elif want_sub_msg:
                            ctx.message.content = want_sub_msg.clean_content
                            want_command = ctx.command.all_commands.get('item')
                            if want_command:
                                return await ctx.invoke(want_command, items=ctx.message.content)
                        break
                    elif want_category_msg.clean_content.lower() == "type":
                        if not user_types:
                            error = _("don't have wants of that type")
                            break
                        want_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/types.png?cache=1")
                        want_embed.clear_fields()
                        want_embed.add_field(name=_('**Remove Alert Subscription**'), value=f"Now, reply with a comma separated list of the types you'd like to unsubscribe from.\n\nYour current want list is: {(', ').join(user_types)}\n\nYou can reply with **cancel** to stop anytime.", inline=False)
                        want_wait = await channel.send(embed=want_embed)
                        try:
                            want_sub_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            want_sub_msg = None
                        await utils.safe_delete(want_wait)
                        if not want_sub_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(want_sub_msg)
                        if want_sub_msg.clean_content.lower() == "cancel":
                            error = _("cancelled your request")
                            break
                        elif want_sub_msg:
                            ctx.message.content = want_sub_msg.clean_content
                            want_command = ctx.command.all_commands.get('type')
                            if want_command:
                                return await ctx.invoke(want_command, types=ctx.message.content)
                        break
                    elif want_category_msg.clean_content.lower() == "role" and user_roles:
                        if not user_roles:
                            error = _("don't have wants of that type")
                            break
                        want_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/discord.png?cache=1")
                        want_embed.clear_fields()
                        role_list = [x.mention for x in user_roles]
                        want_embed.add_field(name=_('**Remove Alert Subscription**'), value=f"Now, reply with a comma separated list of the roles you'd like to unsubscribe from.\n\nYour current roles are: {(', ').join(role_list)}\n\nYou can reply with **cancel** to stop anytime.", inline=False)
                        want_wait = await channel.send(embed=want_embed)
                        try:
                            want_sub_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            want_sub_msg = None
                        await utils.safe_delete(want_wait)
                        if not want_sub_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(want_sub_msg)
                        if want_sub_msg.clean_content.lower() == "cancel":
                            error = _("cancelled your request")
                            break
                        elif want_sub_msg:
                            ctx.message.content = want_sub_msg.clean_content
                            want_command = ctx.command.all_commands.get('role')
                            if want_command:
                                return await ctx.invoke(want_command, roles=ctx.message.content)
                        break
                    elif want_category_msg.clean_content.lower() == "all":
                        want_command = ctx.command.all_commands.get('all')
                        if want_command:
                            return await want_command.invoke(ctx)
                    else:
                        error = _("entered something invalid")
                        break
        if error:
            want_embed.clear_fields()
            want_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/ic_softbank.png?cache=1")
            want_embed.add_field(name=_('**Alert Unsubscription Cancelled**'), value=_("Meowth! Your request has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await channel.send(embed=want_embed, delete_after=10)
            await utils.safe_delete(message)
            return

    @unwant.command(name="pokemon", hidden=True)
    @checks.allowwant()
    async def unwant_pokemon(self, ctx, *, pokemon):
        await self._unwant_pokemon(ctx, pokemon)

    async def _unwant_pokemon(self, ctx, pokemon):
        await ctx.trigger_typing()
        message = ctx.message
        author = message.author
        guild = message.guild
        channel = message.channel
        user_link = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('settings', {}).setdefault('link', True)
        unwant_split = pokemon.lower().split(',')
        unwant_list = []
        removed_count = 0
        spellcheck_dict = {}
        spellcheck_list = []
        not_wanted_count = 0
        not_wanted_list = []
        removed_list = []
        category = "pokemon"
        want_embed = discord.Embed(colour=ctx.me.colour)
        if "boss" in ctx.invoked_with:
            user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('bosses', [])
            user_forms = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('boss_forms', [])
            want_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/eggs/5.png?cache=1")
            category = "boss"
            if user_link:
                return await message.channel.send(f"{ctx.author.mention} - Your boss list is linked to your want list, please use **!unwant** to add pokemon.")
        if "trade" in ctx.invoked_with:
            user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('trades', [])
            user_forms = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('trade_forms', [])
            want_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/eggs/5.png?cache=1")
            category = "trade"
            if user_link:
                return await message.channel.send(f"{ctx.author.mention} - Your boss list is linked to your want list, please use **!unwant** to add pokemon.")
        else:
            user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('wants', [])
            user_forms = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('forms', [])
            want_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/ic_grass.png?cache=1")
        for entered_unwant in unwant_split:
            if entered_unwant.lower() in self.bot.form_dict['list'] and not entered_unwant.isdigit():
                forms = []
                for pokemon in self.bot.form_dict:
                    if pokemon == "list" or pokemon == "two_words":
                        continue
                    if self.bot.form_dict[pokemon].get(entered_unwant.lower()):
                        forms.append(f"{entered_unwant} {utils.get_name(self.bot, pokemon)}")
                forms = [await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, x) for x in forms]
                unwant_list.extend([x for x in forms if x])
                continue
            pokemon = await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, entered_unwant.strip(), allow_digits=True)
            if str(pokemon) == "XS Rattata":
                sizes = [await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, x) for x in ["Alolan XS Rattata", "Male XS Rattata", "Female XS Rattata", "XS Rattata"]]
                unwant_list.extend(sizes)
                continue
            if str(pokemon) == "XL Magikarp":
                sizes = [await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, x) for x in ["Male XL Magikarp", "Female XL Magikarp", "XL Magikarp"]]
                unwant_list.extend(sizes)
                continue
            if pokemon:
                unwant_list.append(pokemon)
            elif len(unwant_split) == 1 and "all" in entered_unwant:
                await utils.safe_delete(ctx.message)
                return await ctx.invoke(self.bot.get_command('unwant all'), category=category)
            elif len(unwant_split) == 1 and "list" in entered_unwant:
                await utils.safe_delete(ctx.message)
                return await ctx.invoke(self.bot.get_command('list wants'))
            else:
                spellcheck_list.append(entered_unwant)
                match, score = utils.get_match(ctx.bot.pkmn_list, entered_unwant)
                spellcheck_dict[entered_unwant] = match
        for entered_unwant in unwant_list:
            boss_str = ""
            if entered_unwant.id in self.bot.raid_list and (user_link or "boss" in ctx.invoked_with):
                boss_str = f" (Level {entered_unwant.raid_level} Boss)"
            if (entered_unwant.size or entered_unwant.gender or entered_unwant.form or entered_unwant.region or entered_unwant.shiny or entered_unwant.shadow) and len(str(entered_unwant).split()) > 1:
                if str(entered_unwant) not in user_forms:
                    not_wanted_list.append(str(entered_unwant))
                    not_wanted_count += 1
                else:
                    user_forms.remove(str(entered_unwant))
                    removed_list.append(f"{str(entered_unwant)}{boss_str}")
                    removed_count += 1
            else:
                if entered_unwant.id not in user_wants:
                    not_wanted_list.append(entered_unwant.name.title())
                    not_wanted_count += 1
                else:
                    user_wants.remove(entered_unwant.id)
                    removed_list.append(f"{entered_unwant.name.title()}{boss_str}")
                    removed_count += 1
        unwant_count = removed_count + not_wanted_count + len(spellcheck_dict)
        confirmation_msg = f"Meowth! {ctx.author.display_name}, out of your total **{unwant_count}** {'boss' if 'boss' in ctx.invoked_with else 'pokemon'}{'es' if unwant_count > 1 and 'boss' in ctx.invoked_with else ''}:\n\n"
        if removed_count > 0:
            confirmation_msg += _('**{removed_count} Removed:** \n\t{removed_list}\n').format(removed_count=removed_count, removed_list=', '.join(removed_list))
        if not_wanted_count > 0:
            confirmation_msg += _('**{not_wanted_count} Not Wanted:** \n\t{not_wanted_list}\n').format(not_wanted_count=not_wanted_count, not_wanted_list=', '.join(not_wanted_list))
        if spellcheck_dict:
            spellcheckmsg = ''
            for word in spellcheck_dict:
                spellcheckmsg += _('\n\t{word}').format(word=word)
                if spellcheck_dict[word]:
                    spellcheckmsg += _(': *({correction}?)*').format(correction=spellcheck_dict[word])
            confirmation_msg += _('**{count} Not Valid:**').format(count=len(spellcheck_dict)) + spellcheckmsg
        if len(removed_list) == 1:
            pokemon = await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, removed_list[0])
            want_embed.set_thumbnail(url=pokemon.img_url)
        want_embed.add_field(name=_('**Remove Alert Subscription**'), value=confirmation_msg, inline=False)
        unwant_confirmation = await channel.send(embed=want_embed)

    @unwant.command(name='boss', aliases=['bosses'])
    @checks.allowwant()
    async def unwant_boss(self, ctx, *, bosses):
        """Remove a boss from your wanted list.

        Usage: !unwant boss <species>
        You will no longer be notified of reports about this Pokemon."""
        await ctx.invoke(self.bot.get_command('unwant pokemon'), pokemon=bosses)

    @unwant.command(name='trade', aliases=['trades'])
    @checks.allowwant()
    async def unwant_trade(self, ctx, *, trades):
        """Remove a trade listing from your wanted list.

        Usage: !unwant trade <species>
        You will no longer be notified of trades about this Pokemon."""
        if not checks.check_tradeset(ctx):
            return await ctx.send(f"Meowth! Trading isn't enabled on this server!", delete_after=30)
        await ctx.invoke(self.bot.get_command('unwant pokemon'), pokemon=trades)

    async def _unwant_poi(self, ctx, pois, poi_type="gym"):
        await ctx.trigger_typing()
        message = ctx.message
        guild = message.guild
        channel = message.channel
        unwant_split = pois.lower().split(',')
        unwant_list = []
        removed_count = 0
        spellcheck_dict = {}
        spellcheck_list = []
        not_wanted_count = 0
        not_wanted_list = []
        removed_list = []
        want_embed = discord.Embed(colour=ctx.me.colour)
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        if not gym_matching_cog:
            return
        if poi_type == "stop":
            pois = gym_matching_cog.get_stops(ctx.guild.id)
            user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('stops', [])
            want_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/pokestop_near.png?cache=1")
        else:
            pois = gym_matching_cog.get_gyms(ctx.guild.id)
            user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('gyms', [])
            want_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/gym-arena.png?cache=1")
        for entered_unwant in unwant_split:
            gym = await gym_matching_cog.poi_match_prompt(ctx, entered_unwant, pois, None)
            if gym:
                unwant_list.append(gym.lower())
            elif len(unwant_split) == 1 and "all" in entered_unwant:
                await utils.safe_delete(ctx.message)
                return await ctx.invoke(self.bot.get_command('unwant all'), category="gym")
            else:
                spellcheck_list.append(entered_unwant)
                match, score = utils.get_match(pois.keys(), entered_unwant)
                spellcheck_dict[entered_unwant] = match
        for entered_unwant in unwant_list:
            if entered_unwant.lower() not in user_wants:
                not_wanted_list.append(entered_unwant.title())
                not_wanted_count += 1
            else:
                user_wants.remove(entered_unwant.lower())
                removed_list.append(f"{entered_unwant.title()}")
                removed_count += 1
        unwant_count = removed_count + not_wanted_count + len(spellcheck_dict)
        confirmation_msg = f"Meowth! {ctx.author.display_name}, out of your total **{unwant_count}** {'stop' if poi_type == 'stop' else 'gym'}{'s' if unwant_count > 1 else ''}:\n\n"
        if removed_count > 0:
            confirmation_msg += _('**{removed_count} Removed:** \n\t{removed_list}\n').format(removed_count=removed_count, removed_list=', '.join(removed_list))
        if not_wanted_count > 0:
            confirmation_msg += _('**{not_wanted_count} Not Wanted:** \n\t{not_wanted_list}\n').format(not_wanted_count=not_wanted_count, not_wanted_list=', '.join(not_wanted_list))
        if spellcheck_dict:
            spellcheckmsg = ''
            for word in spellcheck_dict:
                spellcheckmsg += _('\n\t{word}').format(word=word)
                if spellcheck_dict[word]:
                    spellcheckmsg += _(': *({correction}?)*').format(correction=spellcheck_dict[word])
            confirmation_msg += _('**{count} Not Valid:**').format(count=len(spellcheck_dict)) + spellcheckmsg
        want_embed.add_field(name=_('**Remove Alert Subscription**'), value=confirmation_msg, inline=False)
        unwant_confirmation = await channel.send(embed=want_embed)

    @unwant.command(name='gym', aliases=['gyms'])
    @checks.allowwant()
    async def unwant_gym(self, ctx, *, gyms):
        """Remove a gym from your wanted list.

        Usage: !unwant gym <gym list>
        You will no longer be notified of reports about this gym."""
        await self._unwant_poi(ctx, gyms, poi_type="gym")

    @unwant.command(name='exraid')
    @checks.allowwant()
    async def unwant_exraid(self, ctx):
        """Remove all EX eligible gyms from your want list. Currently used for raid and raid egg reports.

        Usage: !unwant exraid"""
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        ex_list = []
        if not gym_matching_cog:
            return
        gyms = gym_matching_cog.get_gyms(ctx.guild.id)
        for gym in gyms:
            if "ex" in gyms[gym].get('notes', '').lower():
                if gyms[gym].get('alias'):
                    gym = gyms[gym].get('alias')
                if gym not in ex_list:
                    ex_list.append(gym)
        await self._unwant_poi(ctx, (', ').join(ex_list), poi_type="gym")

    @unwant.command(name='stop', aliases=['pokestop', 'pokestops', 'stops'])
    @checks.allowwant()
    async def unwant_stop(self, ctx, *, stops):
        """Remove a pokestop from your wanted list.

        Usage: !unwant stop <stop list>
        You will no longer be notified of reports about this pokestop."""
        await self._unwant_poi(ctx, stops, poi_type="stop")

    @unwant.command(name='item', aliases=['items'])
    @checks.allowwant()
    async def unwant_item(self, ctx, *, items):
        """Remove a item from your wanted list.

        Usage: !unwant item <item list>
        You will no longer be notified of reports about this item."""
        await ctx.trigger_typing()
        message = ctx.message
        guild = message.guild
        channel = message.channel
        unwant_split = items.lower().split(',')
        unwant_list = []
        removed_count = 0
        spellcheck_dict = {}
        spellcheck_list = []
        not_wanted_count = 0
        not_wanted_list = []
        removed_list = []
        want_embed = discord.Embed(colour=ctx.me.colour).set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/MysteryItem.png?cache=1")
        user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('items', [])
        for entered_unwant in unwant_split:
            if entered_unwant.strip().lower() in self.bot.item_list:
                unwant_list.append(entered_unwant.strip().lower())
            elif len(unwant_split) == 1 and "all" in entered_unwant:
                await utils.safe_delete(ctx.message)
                return await ctx.invoke(self.bot.get_command('unwant all'), category="item")
            else:
                match = await utils.autocorrect(self.bot, entered_unwant, self.bot.item_list, ctx.channel, ctx.author)
                if match:
                    unwant_list.append(match)
                else:
                    spellcheck_list.append(entered_unwant)
                    match, score = utils.get_match(self.bot.item_list, entered_unwant)
                    spellcheck_dict[entered_unwant] = match
        for entered_unwant in unwant_list:
            if entered_unwant.lower() not in user_wants:
                not_wanted_list.append(entered_unwant.title())
                not_wanted_count += 1
            else:
                user_wants.remove(entered_unwant.lower())
                removed_list.append(f"{entered_unwant.title()}")
                removed_count += 1
        unwant_count = removed_count + not_wanted_count + len(spellcheck_dict)
        confirmation_msg = _('Meowth! {member}, out of your total **{count}** item{s}:\n\n').format(member=ctx.author.display_name, count=unwant_count, s="s" if unwant_count > 1 else "")
        if removed_count > 0:
            confirmation_msg += _('**{removed_count} Removed:** \n\t{removed_list}\n').format(removed_count=removed_count, removed_list=', '.join(removed_list))
        if not_wanted_count > 0:
            confirmation_msg += _('**{not_wanted_count} Not Wwanted:** \n\t{not_wanted_list}\n').format(not_wanted_count=not_wanted_count, not_wanted_list=', '.join(not_wanted_list))
        if spellcheck_dict:
            spellcheckmsg = ''
            for word in spellcheck_dict:
                spellcheckmsg += _('\n\t{word}').format(word=word)
                if spellcheck_dict[word]:
                    spellcheckmsg += _(': *({correction}?)*').format(correction=spellcheck_dict[word])
            confirmation_msg += _('**{count} Not Valid:**').format(count=len(spellcheck_dict)) + spellcheckmsg
        if len(removed_list) == 1:
            thumbnail_url, item = await utils.get_item(removed_list[0])
            want_embed.set_thumbnail(url=thumbnail_url)
        want_embed.add_field(name=_('**Remove Alert Subscription**'), value=confirmation_msg, inline=False)
        unwant_confirmation = await channel.send(embed=want_embed)

    @unwant.command(name='type', aliases=['types'])
    @checks.allowwant()
    async def unwant_type(self, ctx, *, types):
        """Remove a type from your wanted list.

        Usage: !unwant type <species>
        You will no longer be notified of reports about this type."""
        await ctx.trigger_typing()
        message = ctx.message
        guild = message.guild
        channel = message.channel
        unwant_split = types.lower().split(',')
        unwant_list = []
        removed_count = 0
        spellcheck_dict = {}
        spellcheck_list = []
        not_wanted_count = 0
        not_wanted_list = []
        removed_list = []
        want_embed = discord.Embed(colour=ctx.me.colour).set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/types.png?cache=1")
        user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('types', [])
        for entered_unwant in unwant_split:
            if entered_unwant.strip().lower() in self.bot.type_list:
                unwant_list.append(entered_unwant.strip().lower())
            elif len(unwant_split) == 1 and "all" in entered_unwant:
                await utils.safe_delete(ctx.message)
                return await ctx.invoke(self.bot.get_command('unwant all'), category="type")
            else:
                match = await utils.autocorrect(self.bot, entered_unwant, self.bot.type_list, ctx.channel, ctx.author)
                if match:
                    unwant_list.append(match)
                else:
                    spellcheck_list.append(entered_unwant)
                    match, score = utils.get_match(self.bot.type_list, entered_unwant)
                    spellcheck_dict[entered_unwant] = match
        for entered_unwant in unwant_list:
            if entered_unwant.lower() not in user_wants:
                not_wanted_list.append(entered_unwant.title())
                not_wanted_count += 1
            else:
                user_wants.remove(entered_unwant.lower())
                removed_list.append(f"{entered_unwant.title()}")
                removed_count += 1
        unwant_count = removed_count + not_wanted_count + len(spellcheck_dict)
        confirmation_msg = _('Meowth! {member}, out of your total **{count}** type{s}:\n\n').format(member=ctx.author.display_name, count=unwant_count, s="s" if unwant_count > 1 else "")
        if removed_count > 0:
            confirmation_msg += _('**{removed_count} Removed:** \n\t{removed_list}\n').format(removed_count=removed_count, removed_list=', '.join(removed_list))
        if not_wanted_count > 0:
            confirmation_msg += _('**{not_wanted_count} Not Wanted:** \n\t{not_wanted_list}\n').format(not_wanted_count=not_wanted_count, not_wanted_list=', '.join(not_wanted_list))
        if spellcheck_dict:
            spellcheckmsg = ''
            for word in spellcheck_dict:
                spellcheckmsg += _('\n\t{word}').format(word=word)
                if spellcheck_dict[word]:
                    spellcheckmsg += _(': *({correction}?)*').format(correction=spellcheck_dict[word])
            confirmation_msg += _('**{count} Not Valid:**').format(count=len(spellcheck_dict)) + spellcheckmsg
        if len(removed_list) == 1:
            want_embed.set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/emoji/{removed_list[0].lower()}.png")
        want_embed.add_field(name=_('**Remove Alert Subscription**'), value=confirmation_msg, inline=False)
        unwant_confirmation = await channel.send(embed=want_embed)

    @unwant.command(name='iv', aliases=['ivs'])
    @checks.allowwant()
    async def unwant_iv(self, ctx, *, ivs):
        """Remove an IV from your wanted list.

        Usage: !unwant iv <iv list>
        You will no longer be notified of reports about this IV."""
        await ctx.trigger_typing()
        message = ctx.message
        guild = message.guild
        channel = message.channel
        unwant_split = ivs.lower().split(',')
        unwant_list = []
        removed_count = 0
        not_wanted_count = 0
        not_wanted_list = []
        removed_list = []
        error_list = []
        want_embed = discord.Embed(colour=ctx.me.colour).set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/trade_tut_strength_adjust.png?cache=1")
        user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('ivs', [])
        for entered_unwant in unwant_split:
            if "+" in entered_unwant.lower():
                entered_unwant = entered_unwant.replace("+", "").strip()
                if not entered_unwant.strip().isdigit():
                    error_list.append(entered_unwant)
                    continue
                for iv in range(int(entered_unwant), 101):
                    if iv not in unwant_list:
                        unwant_list.append(str(iv))
            elif "-" in entered_unwant.lower():
                range_split = entered_unwant.split("-")
                if range_split[0].isdigit() and range_split[1].isdigit() and int(range_split[1]) > int(range_split[0]):
                    for iv in range(int(range_split[0]), int(range_split[1])+1):
                        unwant_list.append(str(iv))
                else:
                    error_list.append(entered_unwant)
            else:
                if len(unwant_split) == 1 and "all" in entered_unwant:
                    await utils.safe_delete(ctx.message)
                    return await ctx.invoke(self.bot.get_command('unwant all'), category="iv")
                elif not entered_unwant.strip().isdigit():
                    error_list.append(entered_unwant)
                    continue
                if entered_unwant not in unwant_list:
                    unwant_list.append(entered_unwant)
        for entered_unwant in unwant_list:
            if int(entered_unwant) not in user_wants:
                not_wanted_list.append(entered_unwant)
                not_wanted_count += 1
            else:
                user_wants.remove(int(entered_unwant))
                removed_list.append(f"{entered_unwant}")
                removed_count += 1
        unwant_count = removed_count + not_wanted_count + len(error_list)
        confirmation_msg = _('Meowth! {member}, out of your total **{count}** iv{s}:\n\n').format(member=ctx.author.display_name, count=unwant_count, s="s" if unwant_count > 1 else "")
        if removed_count > 0:
            confirmation_msg += _('**{removed_count} Removed:** \n\t{removed_list}\n').format(removed_count=removed_count, removed_list=', '.join(removed_list))
        if not_wanted_count > 0:
            confirmation_msg += _('**{not_wanted_count} Not Wanted:** \n\t{not_wanted_list}\n').format(not_wanted_count=not_wanted_count, not_wanted_list=', '.join(not_wanted_list))
        if error_list:
            error_msg = ''
            for word in error_list:
                error_msg += _('\n\t{word}').format(word=word)
            confirmation_msg += _('**{count} Not Valid:**').format(count=len(error_list)) + error_msg
        want_embed.add_field(name=_('**Remove Alert Subscription**'), value=confirmation_msg, inline=False)
        unwant_confirmation = await channel.send(embed=want_embed)

    @unwant.command(name='level', aliases=['levels'])
    @checks.allowwant()
    async def unwant_level(self, ctx, *, levels):
        """Remove a level from your wanted list.

        Usage: !unwant level <level list>
        You will no longer be notified of reports about this level."""
        await ctx.trigger_typing()
        message = ctx.message
        guild = message.guild
        channel = message.channel
        unwant_split = levels.lower().split(',')
        unwant_list = []
        removed_count = 0
        not_wanted_count = 0
        not_wanted_list = []
        removed_list = []
        error_list = []
        want_embed = discord.Embed(colour=ctx.me.colour).set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/trade_tut_strength_adjust.png?cache=1")
        user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('levels', [])
        for entered_unwant in unwant_split:
            if "+" in entered_unwant.lower():
                entered_unwant = entered_unwant.replace("+", "").strip()
                if not entered_unwant.strip().isdigit():
                    error_list.append(entered_unwant)
                    continue
                for level in range(int(entered_unwant), 41):
                    if level not in unwant_list:
                        unwant_list.append(str(level))
            elif "-" in entered_unwant.lower():
                range_split = entered_unwant.split("-")
                if range_split[0].isdigit() and range_split[1].isdigit() and int(range_split[1]) > int(range_split[0]):
                    for level in range(int(range_split[0]), int(range_split[1])+1):
                        unwant_list.append(str(level))
                else:
                    error_list.append(entered_unwant)
            else:
                if len(unwant_split) == 1 and "all" in entered_unwant:
                    await utils.safe_delete(ctx.message)
                    return await ctx.invoke(self.bot.get_command('unwant all'), category="level")
                elif not entered_unwant.strip().isdigit():
                    error_list.append(entered_unwant)
                    continue
                if entered_unwant not in unwant_list:
                    unwant_list.append(entered_unwant)
        for entered_unwant in unwant_list:
            if int(entered_unwant) not in user_wants:
                not_wanted_list.append(entered_unwant)
                not_wanted_count += 1
            else:
                user_wants.remove(int(entered_unwant))
                removed_list.append(f"{entered_unwant}")
                removed_count += 1
        unwant_count = removed_count + not_wanted_count + len(error_list)
        confirmation_msg = _('Meowth! {member}, out of your total **{count}** level{s}:\n\n').format(member=ctx.author.display_name, count=unwant_count, s="s" if unwant_count > 1 else "")
        if removed_count > 0:
            confirmation_msg += _('**{removed_count} Removed:** \n\t{removed_list}\n').format(removed_count=removed_count, removed_list=', '.join(removed_list))
        if not_wanted_count > 0:
            confirmation_msg += _('**{not_wanted_count} Not Wanted:** \n\t{not_wanted_list}\n').format(not_wanted_count=not_wanted_count, not_wanted_list=', '.join(not_wanted_list))
        if error_list:
            error_msg = ''
            for word in error_list:
                error_msg += _('\n\t{word}').format(word=word)
            confirmation_msg += _('**{count} Not Valid:**').format(count=len(error_list)) + error_msg
        want_embed.add_field(name=_('**Remove Alert Subscription**'), value=confirmation_msg, inline=False)
        unwant_confirmation = await channel.send(embed=want_embed)

    @unwant.command(name='egg', aliases=["eggs", "raidegg", "raideggs"])
    @checks.allowwant()
    async def unwant_raidegg(self, ctx, *, levels):
        """Remove raid egg levels from subscription list.

        Usage: !unwant egg <1 to 5 or EX>"""
        await ctx.trigger_typing()
        message = ctx.message
        guild = message.guild
        channel = message.channel
        want_split = levels.lower().split(',')
        want_list = []
        removed_count = 0
        not_wanted_count = 0
        not_wanted_list = []
        removed_list = []
        error_list = []
        want_embed = discord.Embed(colour=ctx.me.colour).set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/eggs/5.png?cache=1")
        user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('raid_eggs', [])
        for entered_unwant in want_split:
            if entered_unwant.isdigit() and int(entered_unwant.strip()) > 5:
                error_list.append(entered_unwant)
                continue
            if not entered_unwant.strip().isdigit() and entered_unwant.lower() != "ex":
                error_list.append(entered_unwant)
                continue
            if entered_unwant not in want_list:
                want_list.append(entered_unwant)
        for entered_unwant in want_list:
            if entered_unwant not in user_wants:
                not_wanted_list.append(entered_unwant)
                not_wanted_count += 1
            else:
                user_wants.remove(entered_unwant)
                removed_list.append(f"{entered_unwant}")
                removed_count += 1
        unwant_count = removed_count + not_wanted_count + len(error_list)
        confirmation_msg = _('Meowth! {member}, out of your total **{count}** raid egg{s}:\n\n').format(member=ctx.author.display_name, count=unwant_count, s="s" if unwant_count > 1 else "")
        if removed_count > 0:
            confirmation_msg += _('**{removed_count} Removed:** \n\t{removed_list}\n').format(removed_count=removed_count, removed_list=', '.join(removed_list))
        if not_wanted_count > 0:
            confirmation_msg += _('**{not_wanted_count} Not Wanted:** \n\t{not_wanted_list}\n').format(not_wanted_count=not_wanted_count, not_wanted_list=', '.join(not_wanted_list))
        if error_list:
            error_msg = ''
            for word in error_list:
                error_msg += _('\n\t{word}').format(word=word)
            confirmation_msg += _('**{count} Not Valid:**').format(count=len(error_list)) + error_msg
        want_embed.add_field(name=_('**Remove Alert Subscription**'), value=confirmation_msg, inline=False)
        unwant_confirmation = await channel.send(embed=want_embed)

    @unwant.command(name='role', aliases=['roles'])
    @checks.allowwant()
    async def unwant_role(self, ctx, *, roles):
        """Remove a role from your wanted list.

        Usage: !unwant role <role>"""
        await ctx.trigger_typing()
        message = ctx.message
        guild = message.guild
        channel = message.channel
        unwant_split = roles.lower().split(',')
        unwant_list = []
        removed_count = 0
        spellcheck_dict = {}
        spellcheck_list = []
        not_wanted_count = 0
        not_wanted_list = []
        removed_list = []
        role_list = []
        want_embed = discord.Embed(colour=ctx.me.colour).set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/discord.png?cache=1")
        converter = commands.RoleConverter()
        join_roles = [guild.get_role(x) for x in self.bot.guild_dict[guild.id]['configure_dict'].get('want', {}).get('roles', [])]
        for entered_unwant in unwant_split:
            if len(unwant_split) == 1 and "all" in entered_unwant:
                await utils.safe_delete(ctx.message)
                return await ctx.invoke(self.bot.get_command('unwant all'), category="role")
            try:
                role = await converter.convert(ctx, entered_unwant)
            except:
                role = None
            if role:
                unwant_list.append(role)
            else:
                match, score = utils.get_match([x.name for x in ctx.guild.roles], entered_unwant)
                spellcheck_dict[entered_unwant] = match
        for role in unwant_list:
            role_str = ""
            if role in join_roles:
                role_str = f" ({role.mention})"
                if role in ctx.author.roles:
                    role_list.append(role)
                    removed_list.append(f"{role.name}{role_str}")
                    removed_count += 1
                else:
                    not_wanted_list.append(f"{role.name}{role_str}")
                    not_wanted_count += 1
            else:
                spellcheck_dict[role.name] = None
        await ctx.author.remove_roles(*role_list)
        unwant_count = removed_count + not_wanted_count + len(spellcheck_dict)
        confirmation_msg = _('Meowth! {member}, out of your total **{count}** role{s}:\n\n').format(member=ctx.author.display_name, count=unwant_count, s="es" if unwant_count > 1 else "")
        if removed_count > 0:
            confirmation_msg += _('**{removed_count} Removed:** \n\t{removed_list}\n').format(removed_count=removed_count, removed_list=', '.join(removed_list))
        if not_wanted_count > 0:
            confirmation_msg += _('**{not_wanted_count} Not Wanted:** \n\t{not_wanted_list}\n').format(not_wanted_count=not_wanted_count, not_wanted_list=', '.join(not_wanted_list))
        if spellcheck_dict:
            spellcheckmsg = ''
            for word in spellcheck_dict:
                spellcheckmsg += _('\n\t{word}').format(word=word)
                if spellcheck_dict[word]:
                    spellcheckmsg += _(': *({correction}?)*').format(correction=spellcheck_dict[word])
            confirmation_msg += _('**{count} Not Valid:**').format(count=len(spellcheck_dict)) + spellcheckmsg
        want_embed.add_field(name=_('**Remove Alert Subscription**'), value=confirmation_msg, inline=False)
        unwant_confirmation = await channel.send(embed=want_embed)

    @unwant.command(name='all')
    @checks.allowwant()
    async def unwant_all(self, ctx, category="all"):
        """Remove all things from your wanted list.

        Usage: !unwant all
        All wants are removed."""
        message = ctx.message
        guild = message.guild
        channel = message.channel
        author = message.author
        user_wants = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('wants', [])
        user_forms = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('forms', [])
        user_bosses = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('bosses', [])
        user_bossforms = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('boss_forms', [])
        user_trades = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('trades', [])
        user_tradeforms = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('trade_forms', [])
        user_gyms = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('gyms', [])
        user_stops = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('stops', [])
        user_items = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('items', [])
        user_types = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('types', [])
        user_ivs = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('ivs', [])
        user_levels = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('levels', [])
        user_eggs = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('alerts', {}).setdefault('raid_eggs', [])
        join_roles = [guild.get_role(x) for x in self.bot.guild_dict[guild.id]['configure_dict'].get('want', {}).get('roles', [])]
        user_roles = [x for x in join_roles if x in author.roles]
        unwant_msg = ""
        if not any([user_wants, user_bosses, user_gyms, user_stops, user_items, user_types, user_ivs, user_levels, user_forms, user_roles, user_bossforms, user_trades, user_eggs]):
            return await channel.send(content=_('{0}, you have nothing in your want list!').format(author.mention), delete_after=10)
        await channel.trigger_typing()
        completed_list = []
        if(category == "all" or category == "pokemon") and len(user_wants) > 0:
            self.bot.guild_dict[guild.id]['trainers'][message.author.id]['alerts']['wants'] = []
            completed_list.append(f"{len(user_wants)} pokemon")
        if (category == "all" or category == "form") and len(user_forms) > 0:
            self.bot.guild_dict[guild.id]['trainers'][message.author.id]['alerts']['forms'] = []
            completed_list.append(f"{len(user_forms)} form{'s' if len(user_forms) > 1 else ''}")
        if (category == "all" or category == "boss") and len(user_bosses) > 0:
            self.bot.guild_dict[guild.id]['trainers'][message.author.id]['alerts']['bosses'] = []
            completed_list.append(f"{len(user_bosses)} boss{'es' if len(user_bosses) > 1 else ''}")
        if (category == "all" or category == "boss") and len(user_bossforms) > 0:
            self.bot.guild_dict[guild.id]['trainers'][message.author.id]['alerts']['boss_forms'] = []
            completed_list.append(f"{len(user_bosses)} boss form{'s' if len(user_bosses) > 1 else ''}")
        if (category == "all" or category == "trade") and len(user_trades) > 0:
            self.bot.guild_dict[guild.id]['trainers'][message.author.id]['alerts']['trades'] = []
            completed_list.append(f"{len(user_trades)} trade{'s' if len(user_trades) > 1 else ''}")
        if (category == "all" or category == "trade") and len(user_tradeforms) > 0:
            self.bot.guild_dict[guild.id]['trainers'][message.author.id]['alerts']['trade_forms'] = []
            completed_list.append(f"{len(user_tradeforms)} trade form{'s' if len(user_tradeforms) > 1 else ''}")
        if (category == "all" or category == "gym") and len(user_gyms) > 0:
            self.bot.guild_dict[guild.id]['trainers'][message.author.id]['alerts']['gyms'] = []
            completed_list.append(f"{len(user_gyms)} gym{'s' if len(user_gyms) > 1 else ''}")
        if (category == "all" or category == "stop") and len(user_stops) > 0:
            self.bot.guild_dict[guild.id]['trainers'][message.author.id]['alerts']['stops'] = []
            completed_list.append(f"{len(user_stops)} pokestop{'s' if len(user_stops) > 1 else ''}")
        if (category == "all" or category == "item") and len(user_items) > 0:
            self.bot.guild_dict[guild.id]['trainers'][message.author.id]['alerts']['items'] = []
            completed_list.append(f"{len(user_items)} item{'s' if len(user_items) > 1 else ''}")
        if (category == "all" or category == "type") and len(user_types) > 0:
            self.bot.guild_dict[guild.id]['trainers'][message.author.id]['alerts']['types'] = []
            completed_list.append(f"{len(user_types)} type{'s' if len(user_types) > 1 else ''}")
        if (category == "all" or category == "iv") and len(user_ivs) > 0:
            self.bot.guild_dict[guild.id]['trainers'][message.author.id]['alerts']['ivs'] = []
            completed_list.append(f"{len(user_ivs)} IV{'s' if len(user_ivs) > 1 else ''}")
        if (category == "all" or category == "level") and len(user_levels) > 0:
            self.bot.guild_dict[guild.id]['trainers'][message.author.id]['alerts']['levels'] = []
            completed_list.append(f"{len(user_levels)} level{'s' if len(user_levels) > 1 else ''}")
        if (category == "all" or category == "egg") and len(user_eggs) > 0:
            self.bot.guild_dict[guild.id]['trainers'][message.author.id]['alerts']['raid_eggs'] = []
            completed_list.append(f"{len(user_eggs)} raid egg{'s' if len(user_eggs) > 1 else ''}")
        if (category == "all" or category == "role") and len(user_roles) > 0:
            remove_roles = []
            for role in author.roles:
                if role in join_roles:
                    remove_roles.append(role)
            await author.remove_roles(*remove_roles)
            completed_list.append(f"{len(user_roles)} role{'s' if len(user_roles) > 1 else ''}")
        unwant_msg = f"{author.mention} I've removed **{(', ').join(completed_list)}** from your want list."
        await channel.send(unwant_msg)

def setup(bot):
    bot.add_cog(Want(bot))

def teardown(bot):
    bot.remove_cog(Want)
