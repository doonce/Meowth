import asyncio
import copy
import re
import time
import datetime
import dateparser
import textwrap
import logging
import string
import traceback
import aiohttp
import os
import json

import discord
from discord.ext import commands, tasks

from meowth import checks
from meowth.exts import pokemon as pkmn_class
from meowth.exts import utilities as utils

logger = logging.getLogger("meowth")

class Research(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.research_cleanup.start()
        self.auto_res_json.start()

    def cog_unload(self):
        self.research_cleanup.cancel()
        self.auto_res_json.cancel()

    @tasks.loop(seconds=0)
    async def research_cleanup(self, loop=True):
        logger.info('------ BEGIN ------')
        midnight_list = []
        count = 0
        for guild in list(self.bot.guilds):
            if guild.id not in list(self.bot.guild_dict.keys()):
                continue
            try:
                utcnow = (datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
                to_midnight = 24*60*60 - ((utcnow-utcnow.replace(hour=0, minute=0, second=0, microsecond=0)).seconds)
                if to_midnight > 0:
                    midnight_list.append(to_midnight)
                research_dict = self.bot.guild_dict[guild.id].setdefault('questreport_dict', {})
                for reportid in list(research_dict.keys()):
                    if research_dict.get(reportid, {}).get('exp', 0) <= time.time():
                        report_channel = self.bot.get_channel(research_dict.get(reportid, {}).get('report_channel'))
                        if report_channel:
                            try:
                                report_message = await report_channel.fetch_message(reportid)
                                self.bot.loop.create_task(self.expire_research(report_message))
                                count += 1
                                continue
                            except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                                pass
                        try:
                            self.bot.loop.create_task(utils.expire_dm_reports(self.bot, research_dict.get(reportid, {}).get('dm_dict', {})))
                            del self.bot.guild_dict[guild.id]['questreport_dict'][reportid]
                            count += 1
                            continue
                        except KeyError:
                            continue
            except Exception as e:
                print(traceback.format_exc())
        # save server_dict changes after cleanup
        logger.info('SAVING CHANGES')
        try:
            await self.bot.save
        except Exception as err:
            logger.info('SAVING FAILED' + err)
        if not midnight_list:
            midnight_list = [600]
        logger.info(f"------ END - {count} Tasks Cleaned - Waiting {min(midnight_list)} seconds. ------")
        self.research_cleanup.change_interval(seconds=min(midnight_list))
        if not loop:
            return

    @research_cleanup.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        channel = self.bot.get_channel(payload.channel_id)
        guild = getattr(channel, "guild", None)
        if guild and guild.id not in list(self.bot.guild_dict.keys()):
            return
        try:
            user = self.bot.get_user(payload.user_id)
        except AttributeError:
            return
        if user == self.bot.user:
            return
        if guild:
            user = guild.get_member(payload.user_id)
        else:
            return
        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.errors.NotFound, AttributeError, discord.Forbidden):
            return
        can_manage = channel.permissions_for(user).manage_messages
        try:
            research_dict = self.bot.guild_dict[guild.id]['questreport_dict']
        except KeyError:
            research_dict = {}
        if message.id in research_dict:
            research_dict =  self.bot.guild_dict[guild.id]['questreport_dict'][message.id]
            if str(payload.emoji) == self.bot.custom_emoji.get('research_complete', u'\U00002705'):
                if user.id not in research_dict.get('completed_by', []):
                    if user.id != research_dict['report_author']:
                        research_dict.get('completed_by', []).append(user.id)
            elif str(payload.emoji) == self.bot.custom_emoji.get('research_expired', u'\U0001F4A8'):
                for reaction in message.reactions:
                    if reaction.emoji == self.bot.custom_emoji.get('research_expired', u'\U0001F4A8') and (reaction.count >= 3 or can_manage):
                        await self.expire_research(message)
            elif str(payload.emoji) == self.bot.custom_emoji.get('research_info', u'\U00002139\U0000fe0f'):
                ctx = await self.bot.get_context(message)
                if not ctx.prefix:
                    prefix = self.bot._get_prefix(self.bot, message)
                    ctx.prefix = prefix[-1]
                await utils.remove_reaction(message, payload.emoji, user)
                ctx.author, ctx.message.author = user, user
                await self.add_research_info(ctx, message)
            elif str(payload.emoji) == self.bot.custom_emoji.get('research_report', u'\U0001F4E2'):
                ctx = await self.bot.get_context(message)
                ctx.author, ctx.message.author = user, user
                await utils.remove_reaction(message, payload.emoji, user)
                return await ctx.invoke(self.bot.get_command('research'))
            elif str(payload.emoji) == self.bot.custom_emoji.get('list_emoji', u'\U0001f5d2\U0000fe0f'):
                ctx = await self.bot.get_context(message)
                await asyncio.sleep(0.25)
                await utils.remove_reaction(message, payload.emoji, self.bot.user)
                await asyncio.sleep(0.25)
                await utils.remove_reaction(message, payload.emoji, user)
                await ctx.invoke(self.bot.get_command("list research"))
                await asyncio.sleep(5)
                await utils.add_reaction(message, payload.emoji)

    async def expire_research(self, message):
        guild = message.channel.guild
        channel = message.channel
        research_dict = copy.deepcopy(self.bot.guild_dict[guild.id]['questreport_dict'])
        last_report = True if len (self.bot.guild_dict[guild.id]['questreport_dict'].keys()) == 1 else False
        author = guild.get_member(research_dict.get(message.id, {}).get('report_author'))
        cleanup_setting = self.bot.guild_dict[guild.id].get('configure_dict', {}).get('research', {}).setdefault('cleanup_setting', "delete")
        if cleanup_setting == "delete":
            await utils.safe_delete(message)
        else:
            try:
                await message.edit(content=message.content.splitlines()[0], embed=discord.Embed(colour=message.guild.me.colour, description=f"**This quest has expired!**"))
                await message.clear_reactions()
            except:
                pass
        try:
            user_message = await channel.fetch_message(research_dict[message.id]['report_message'])
            await utils.safe_delete(user_message)
        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException, KeyError):
            pass
        await utils.expire_dm_reports(self.bot, research_dict[message.id].get('dm_dict', {}))
        research_bonus = research_dict.get(message.id, {}).get('completed_by', [])
        if len(research_bonus) >= 3 and author and not author.bot:
            research_reports = self.bot.guild_dict[message.guild.id].setdefault('trainers', {}).setdefault(author.id, {}).setdefault('reports', {}).setdefault('research', 0) + 1
            self.bot.guild_dict[message.guild.id]['trainers'][author.id]['reports']['research'] = research_reports
        try:
            del self.bot.guild_dict[guild.id]['questreport_dict'][message.id]
        except KeyError:
            pass
        try:
            ctx = await self.bot.get_context(message)
            if last_report and len (self.bot.guild_dict[guild.id]['questreport_dict'].keys()) == 0:
                await ctx.invoke(self.bot.get_command('list research'))
        except:
            pass

    async def add_research_info(self, ctx, message):
        research_dict = self.bot.guild_dict[ctx.guild.id]['questreport_dict'].get(message.id, {})
        message = ctx.message
        channel = message.channel
        guild = message.guild
        author = guild.get_member(research_dict.get('report_author', None))
        location = research_dict.get('location', '')
        quest = research_dict.get('quest', '')
        reward = research_dict.get('reward', '')
        pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, reward)
        if not author:
            return
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        error = False
        success = []
        reply_msg = f"**pokestop <pokestop name>** - Current: {research_dict.get('location', 'X')}\n"
        reply_msg += f"**quest <quest>** - Current: {research_dict.get('quest', 'X')}\n"
        reply_msg += f"**reward <reward>** - Current: {research_dict.get('reward', 'X')}\n"
        research_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/field-research.png?cache=1')
        research_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        while True:
            async with ctx.typing():
                research_embed.add_field(name=_('**Edit Research Info**'), value=f"Meowth! I'll help you add information to the field research report at **{location}**!\n\nI'll need to know what **values** you'd like to edit. Reply **cancel** to stop anytime or reply with a comma separated list of the following options `Ex: pokestop park bench, quest evolve a pokemon, reward eevee`:\n\n{reply_msg}", inline=False)
                value_wait = await channel.send(embed=research_embed)
                def check(reply):
                    if reply.author is not guild.me and reply.channel.id == channel.id and reply.author == ctx.author:
                        return True
                    else:
                        return False
                try:
                    value_msg = await self.bot.wait_for('message', timeout=60, check=check)
                except asyncio.TimeoutError:
                    value_msg = None
                await utils.safe_delete(value_wait)
                if not value_msg:
                    error = _("took too long to respond")
                    break
                else:
                    await utils.safe_delete(value_msg)
                if value_msg.clean_content.lower() == "cancel":
                    error = _("cancelled the report")
                    break
                else:
                    entered_values = value_msg.clean_content.lower().split(',')
                    entered_values = [x.strip() for x in entered_values]
                    for value in entered_values:
                        value_split = value.split()
                        if len(value_split) < 2:
                            error = _("entered something invalid")
                            continue
                        if "stop" in value and "stop" not in success:
                            if value_split[1]:
                                self.bot.guild_dict[ctx.guild.id]['questreport_dict'][message.id]['location'] = value.replace("pokestop", "").replace("stop", "").strip()
                                success.append("stop")
                            else:
                                error = _('entered something invalid.')
                        elif "quest" in value and "quest" not in success:
                            if value_split[1]:
                                self.bot.guild_dict[ctx.guild.id]['questreport_dict'][message.id]['quest'] = value.replace("quest", "").strip()
                                success.append("quest")
                            else:
                                error = _('entered something invalid.')
                        elif "reward" in value and "reward" not in success:
                            reward_list = ["ball", "nanab", "pinap", "razz", "berr", "stardust", "potion", "revive", "candy", "lure", "module", "mysterious", "component", "radar", "sinnoh", "unova", "stone", "scale", "coat", "grade"]
                            other_reward = any(x in value.lower() for x in reward_list)
                            pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, value)
                            if pokemon and not other_reward:
                                pokemon.shiny = False
                                pokemon.size = None
                                pokemon.gender = None
                                pokemon.shadow = None
                                self.bot.guild_dict[ctx.guild.id]['questreport_dict'][message.id]['reward'] = pokemon.name.lower()
                                success.append("reward")
                            else:
                                __, item = await utils.get_item(value.replace("reward", "").strip())
                                if not item:
                                    item = value.replace("reward", "").strip()
                                self.bot.guild_dict[ctx.guild.id]['questreport_dict'][message.id]['reward'] = item
                                success.append("reward")
                        else:
                            error = _("entered something invalid")
                    break
        if success:
            await self.edit_research_messages(ctx, message)
        elif not error:
            error = _("didn't change anything")
        if error:
            research_embed.clear_fields()
            research_embed.add_field(name=_('**Research Edit Cancelled**'), value=f"Meowth! Your edit has been cancelled because you **{error}**! Retry when you're ready.", inline=False)
            if success:
                research_embed.set_field_at(0, name="**Research Edit Error**", value=f"Meowth! Your **{(', ').join(success)}** edits were successful, but others were skipped because you **{error}**! Retry when you're ready.", inline=False)
            confirmation = await channel.send(embed=research_embed, delete_after=10)

    async def edit_research_messages(self, ctx, message):
        research_dict = self.bot.guild_dict[ctx.guild.id]['questreport_dict'].get(message.id, {})
        dm_dict = research_dict.get('dm_dict', {})
        location = research_dict.get('location', '')
        quest = research_dict.get('quest', '')
        reward = research_dict.get('reward', '')
        pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, reward)
        old_embed = message.embeds[0]
        loc_url = old_embed.url
        author = ctx.guild.get_member(research_dict.get('report_author', None))
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        stop_info = ""
        nearest_stop = ""
        if gym_matching_cog:
            stop_info, location, stop_url = await gym_matching_cog.get_poi_info(ctx, location, "research", dupe_check=False, autocorrect=False)
            if stop_url:
                loc_url = stop_url
                nearest_stop = location
        if not location:
            return
        if author:
            ctx.author, ctx.message.author = author, author
        shiny_str = ""
        if pokemon and "research" in pokemon.shiny_available:
            shiny_str = self.bot.custom_emoji.get('shiny_chance', u'\U00002728') + " "
        reward_list = ["ball", "nanab", "pinap", "razz", "berr", "stardust", "potion", "revive", "candy", "lure", "module", "mysterious", "component", "radar", "sinnoh", "unova", "stone", "scale", "coat", "grade"]
        other_reward = any(x in reward.lower() for x in reward_list)
        if pokemon and not other_reward:
            reward = f"{shiny_str}{string.capwords(reward, ' ')} {pokemon.emoji}"
            pokemon.shiny = False
            pokemon.gender = False
            pokemon.size = False
            pokemon.shadow = False
        research_embed = await self.make_research_embed(ctx, pokemon, stop_info, location, loc_url, quest, reward)
        if pokemon:
            reward = reward.replace(pokemon.emoji, "").replace(shiny_str, "").strip()
        __, item = await utils.get_item(reward)
        content = message.content.splitlines()
        content[0] = f"Meowth! {pokemon.name.title() + ' ' if pokemon else ''}Field Research reported by {ctx.author.mention}! Details: {location}"
        content = ('\n').join(content)
        try:
            await message.edit(content=content, embed=research_embed)
        except:
            pass
        if isinstance(research_embed.description, discord.embeds._EmptyEmbed):
            research_embed.description = ""
        if "Jump to Message" not in research_embed.description:
            research_embed.description = research_embed.description + f"\n**Report:** [Jump to Message]({message.jump_url})"
        new_description = str(research_embed.description)
        index = 0
        for field in research_embed.fields:
            if "reaction" in field.name.lower():
                research_embed.remove_field(index)
            else:
                index += 1
        for dm_user, dm_message in dm_dict.items():
            try:
                dm_user = self.bot.get_user(dm_user)
                dm_channel = dm_user.dm_channel
                if not dm_channel:
                    dm_channel = await dm_user.create_dm()
                if not dm_user or not dm_channel:
                    continue
                dm_message = await dm_channel.fetch_message(dm_message)
                content = f"Meowth! {pokemon.name.title() + ' ' if pokemon else ''}Field Research reported by {ctx.author.display_name} in {ctx.channel.mention}! Details: {location}"
                research_embed.description = dm_message.embeds[0].description
                await dm_message.edit(content=content, embed=research_embed)
            except:
                pass
        research_embed.description = new_description
        ctx.researchreportmsg = message
        dm_dict = await self.send_dm_messages(ctx, pokemon, location, item, copy.deepcopy(research_embed), dm_dict)
        self.bot.guild_dict[ctx.guild.id]['questreport_dict'][message.id]['dm_dict'] = dm_dict

    @tasks.loop(seconds=0)
    async def auto_res_json(self):
        while True:
            try:
                tsr_quests = []
                tsr_quest_dict = {}
                all_quests = {}
                item_quests = {}
                pokemon_quests = {}
                added_categories = []
                added_quests = []
                to_midnight = 24*60*60 - ((datetime.datetime.utcnow()-datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)).seconds)
                to_sixam = 24*60*60 - ((datetime.datetime.utcnow()-datetime.datetime.utcnow().replace(hour=6, minute=0, second=0, microsecond=0)).seconds)
                to_noon = 24*60*60 - ((datetime.datetime.utcnow()-datetime.datetime.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)).seconds)
                to_sixpm = 24*60*60 - ((datetime.datetime.utcnow()-datetime.datetime.utcnow().replace(hour=18, minute=0, second=0, microsecond=0)).seconds)
                try:
                    await asyncio.sleep(min([to_sixpm, to_sixam, to_midnight, to_noon]))
                except asyncio.CancelledError:
                    break
                async with aiohttp.ClientSession() as sess:
                    async with sess.get("https://thesilphroad.com/research-tasks") as resp:
                        html = await resp.text()
                parse_list = re.split('<div|<span|<p', str(html))
                for line in parse_list:
                    if "Tasks</h3>" in line or "class=\"taskText\">" in line or "class=\"task-reward" in line:
                        for replacement in ["</h3", "class=\"taskText\">", "class=\"task-reward", "<img src=\"https://assets.thesilphroad.com/img/pokemon/icons/96x96/", ".png", "<br>", "\">", "class=\"task-group", "group1", "group2", "group3", "group4", "group5", "group6", "group7", "group8", "group9", "<h3>", "</p>", ">", "unconfirmed", "pokemon", "shinyAvailable",]:
                            line = line.replace(replacement, "").replace("_", " ").strip()
                        tsr_quests.append(line.strip())
                for index, item in enumerate(tsr_quests):
                    if len(item.split()) > 2:
                        continue
                    __, item_name = await utils.get_item(item)
                    if item_name:
                        tsr_quests[index] = item_name
                for item in tsr_quests:
                    if "Tasks" in item:
                        all_quests[item] = {}
                        added_categories.append(item)
                for item in tsr_quests:
                    if len(item.split('-')) > 1 and (item.split('-')[0].lower() in self.bot.pkmn_list or item.split('-')[1].lower() in self.bot.pkmn_list):
                        continue
                    if item in added_categories or item.isdigit() or item.lower() in self.bot.item_list:
                        continue
                    for category in all_quests.keys():
                        all_quests[category][item] = []
                        if item not in added_quests:
                            added_quests.append(item)
                for item in tsr_quests:
                    if item in added_categories:
                        current_category = item
                        all_quests[item] = {}
                        continue
                    elif item in added_quests:
                        current_quest = item
                        all_quests[current_category][item] = []
                        continue
                    else:
                        if not item in self.bot.item_list and not item in added_quests and not item in added_categories:
                            shiny_str = ""
                            if item.isdigit():
                                pokemon = utils.get_name(self.bot, item)
                                if pokemon:
                                    pokemon_shiny = self.bot.pkmn_info[pokemon]['forms']['none']['shiny']
                                    if "research" in pokemon_shiny:
                                        shiny_str = self.bot.custom_emoji.get('shiny_chance', u'\U00002728') + " "
                                    pokemon_types = [utils.type_to_emoji(self.bot, x) for x in self.bot.pkmn_info[pokemon]['forms']['none']['type']]
                                    item = f"{shiny_str}{pokemon.title()} {(''.join(pokemon_types))}"
                            else:
                                pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, item, allow_digits=True)
                                if pokemon:
                                    if "research" in pokemon.shiny_available:
                                        shiny_str = self.bot.custom_emoji.get('shiny_chance', u'\U00002728') + " "
                                    item = f"{shiny_str}{str(pokemon)} {pokemon.emoji}"
                            setup_var = pokemon_quests.setdefault(current_category, {}).setdefault(current_quest, [])
                            pokemon_quests[current_category][current_quest].append(item)
                        else:
                            setup_var = item_quests.setdefault(current_category, {}).setdefault(current_quest, [])
                            item_quests[current_category][current_quest].append(item)
                        all_quests[current_category][current_quest].append(item)
                tsr_quest_dict = {"all": all_quests, "pokemon": pokemon_quests, "items": item_quests, "last_edit": time.time()}
                data = json.dumps(tsr_quest_dict)
                json.loads(data)
                if tsr_quest_dict:
                    with open(os.path.join('data', 'quest_info.json'), 'w') as fd:
                        json.dump(tsr_quest_dict, fd, indent=2, separators=(', ', ': '))
            except Exception as e:
                print(traceback.format_exc())

    @auto_res_json.before_loop
    async def before_auto_res_json(self):
        await self.bot.wait_until_ready()

    @commands.command()
    @checks.is_manager()
    async def res_json(self, ctx):
        tsr_quests = []
        tsr_quest_dict = {}
        all_quests = {}
        pokemon_quests = {}
        item_quests = {}
        added_categories = []
        added_quests = []
        error = False
        async with ctx.typing():
            async with aiohttp.ClientSession() as sess:
                async with sess.get("https://thesilphroad.com/research-tasks") as resp:
                    html = await resp.text()
            parse_list = re.split('<div|<span|<p', str(html))
            for line in parse_list:
                if "Tasks</h3>" in line or "class=\"taskText\">" in line or "class=\"task-reward" in line:
                    for replacement in ["</h3", "class=\"taskText\">", "class=\"task-reward", "<img src=\"https://assets.thesilphroad.com/img/pokemon/icons/96x96/", ".png", "<br>", "\">", "class=\"task-group", "group1", "group2", "group3", "group4", "group5", "group6", "group7", "group8", "group9", "<h3>", "</p>", ">", "unconfirmed", "pokemon", "shinyAvailable",]:
                        line = line.replace(replacement, "").replace("_", " ").strip()
                    tsr_quests.append(line.strip())
            for index, item in enumerate(tsr_quests):
                if len(item.split()) > 2:
                    continue
                __, item_name = await utils.get_item(item)
                if item_name:
                    tsr_quests[index] = item_name
            for item in tsr_quests:
                if "Tasks" in item:
                    all_quests[item] = {}
                    added_categories.append(item)
            for item in tsr_quests:
                if len(item.split('-')) > 1 and (item.split('-')[0].lower() in self.bot.pkmn_list or item.split('-')[1].lower() in self.bot.pkmn_list):
                    continue
                if item in added_categories or item.isdigit() or item.lower() in self.bot.item_list:
                    continue
                for category in all_quests.keys():
                    all_quests[category][item] = []
                    if item not in added_quests:
                        added_quests.append(item)
            for item in tsr_quests:
                if item in added_categories:
                    current_category = item
                    all_quests[item] = {}
                    continue
                elif item in added_quests:
                    current_quest = item
                    all_quests[current_category][item] = []
                    continue
                else:
                    if not item in self.bot.item_list and not item in added_quests and not item in added_categories:
                        shiny_str = ""
                        if item.isdigit():
                            pokemon = utils.get_name(self.bot, item)
                            if pokemon:
                                pokemon_shiny = self.bot.pkmn_info[pokemon]['forms']['none']['shiny']
                                if "research" in pokemon_shiny:
                                    shiny_str = self.bot.custom_emoji.get('shiny_chance', u'\U00002728') + " "
                                pokemon_types = [utils.type_to_emoji(self.bot, x) for x in self.bot.pkmn_info[pokemon]['forms']['none']['type']]
                                item = f"{shiny_str}{pokemon.title()} {(''.join(pokemon_types))}"
                        else:
                            pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, item, allow_digits=True)
                            if pokemon:
                                if "research" in pokemon.shiny_available:
                                    shiny_str = self.bot.custom_emoji.get('shiny_chance', u'\U00002728') + " "
                                item = f"{shiny_str}{str(pokemon)} {pokemon.emoji}"
                        setup_var = pokemon_quests.setdefault(current_category, {}).setdefault(current_quest, [])
                        pokemon_quests[current_category][current_quest].append(item)
                    else:
                        setup_var = item_quests.setdefault(current_category, {}).setdefault(current_quest, [])
                        item_quests[current_category][current_quest].append(item)
                    all_quests[current_category][current_quest].append(item)
            tsr_quest_dict = {"all": all_quests, "pokemon": pokemon_quests, "items": item_quests, "last_edit": time.time()}
            research_embed = discord.Embed(discription="", colour=ctx.guild.me.colour)
            for category in tsr_quest_dict['all'].keys():
                field_value = ""
                for quest in tsr_quest_dict['all'][category]:
                    if (len(field_value) + len(f"**{quest}** - {(', ').join([x.title() for x in tsr_quest_dict['all'][category][quest]])}\n")) >= 1020:
                        research_embed.add_field(name=category, value=field_value, inline=False)
                        await ctx.send(embed=research_embed, delete_after=60)
                        research_embed.clear_fields()
                        field_value = ""
                    field_value += f"**{quest}** - {(', ').join([x.title() for x in tsr_quest_dict['all'][category][quest]])}\n"
                research_embed.add_field(name=category, value=field_value, inline=False)
            await ctx.send(embed=research_embed, delete_after=60)
            question = await ctx.send(f"This will be the new research dictionary. The above messages will delete themselves, but they will be in **{ctx.prefix}list tasks**. Continue?")
            research_embed.set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/field-research.png?cache=1')
            try:
                timeout = False
                res, reactuser = await utils.ask(self.bot, question, ctx.author.id)
            except TypeError:
                timeout = True
            if timeout or res.emoji == self.bot.custom_emoji.get('answer_no', u'\U0000274e'):
                await utils.safe_delete(question)
                error = _('cancelled the command')
            elif res.emoji == self.bot.custom_emoji.get('answer_yes', u'\U00002705'):
                pass
            else:
                error = _('did something invalid')
            await utils.safe_delete(question)
            if error:
                research_embed.clear_fields()
                research_embed.add_field(name=_('**Quest Edit Cancelled**'), value=_("Meowth! Your edit has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
                confirmation = await ctx.send(embed=research_embed, delete_after=10)
                await utils.safe_delete(ctx.message)
            else:
                try:
                    data = json.dumps(tsr_quest_dict)
                    json.loads(data)
                except:
                    research_embed.clear_fields()
                    research_embed.add_field(name=_('**Quest Edit Cancelled**'), value=_("Meowth! Your edit has been cancelled because TSR didn't respond correctly! Retry when you're ready."), inline=False)
                    return await ctx.send(embed=research_embed, delete_after=10)
                research_embed.clear_fields()
                research_embed.add_field(name=_('**Quest Edit Completed**'), value=_("Meowth! Your edit completed successfully.").format(error=error), inline=False)
                confirmation = await ctx.send(embed=research_embed)
                with open(os.path.join('data', 'quest_info.json'), 'w') as fd:
                    json.dump(tsr_quest_dict, fd, indent=2, separators=(', ', ': '))

    @commands.group(aliases=['res'], invoke_without_command=True, case_insensitive=True)
    @checks.allowresearchreport()
    async def research(self, ctx, *, details = None):
        """Report Field research
        Guided report method with just !research. If you supply arguments in one
        line, avoid commas in anything but your separations between pokestop,
        quest, reward. Order matters if you supply arguments. If a pokemon name
        is included in reward, a @mention will be used if role exists.

        Usage: !research [pokestop name [optional URL], quest, reward]"""
        message = ctx.message
        channel = message.channel
        author = message.author
        guild = message.guild
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        error = False
        loc_url = utils.create_gmaps_query(self.bot, "", message.channel, type="research")
        research_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/field-research.png?cache=1')
        research_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        pokemon = False
        research_dict = self.bot.guild_dict[ctx.guild.id].setdefault('questreport_dict', {})
        while True:
            async with ctx.typing():
                if details:
                    research_split = details.rsplit(",", 2)
                    research_split = [x.strip() for x in research_split]
                    if len(research_split) != 3:
                        return await ctx.invoke(self.bot.get_command('research'))
                    location, quest, reward = research_split
                    location = location.replace(loc_url, "").strip()
                    loc_url = utils.create_gmaps_query(self.bot, location, message.channel, type="research")
                    gym_matching_cog = self.bot.cogs.get('GymMatching')
                    stop_info = ""
                    if gym_matching_cog:
                        stop_info, location, stop_url = await gym_matching_cog.get_poi_info(ctx, location, "research")
                        if stop_url:
                            loc_url = stop_url
                    if not location:
                        return
                    break
                else:
                    research_embed.add_field(name=_('**New Research Report**'), value=_("Meowth! I'll help you report a research quest!\n\nFirst, I'll need to know what **pokestop** you received the quest from. Reply with the name of the **pokestop**. You can reply with **cancel** to stop anytime."), inline=False)
                    pokestopwait = await channel.send(embed=research_embed)
                    def check(reply):
                        if reply.author is not guild.me and reply.channel.id == channel.id and reply.author == message.author:
                            return True
                        else:
                            return False
                    try:
                        pokestopmsg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        pokestopmsg = None
                    await utils.safe_delete(pokestopwait)
                    if not pokestopmsg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(pokestopmsg)
                    if pokestopmsg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif pokestopmsg:
                        location = pokestopmsg.clean_content
                        loc_url = utils.create_gmaps_query(self.bot, location, message.channel, type="research")
                        location = location.replace(loc_url, "").strip()
                        gym_matching_cog = self.bot.cogs.get('GymMatching')
                        stop_info = ""
                        if gym_matching_cog:
                            stop_info, location, stop_url = await gym_matching_cog.get_poi_info(ctx, location, "research")
                            if stop_url:
                                loc_url = stop_url
                        if not location:
                            return
                    research_embed.set_field_at(0, name=research_embed.fields[0].name, value=_("Great! Now, reply with the **quest** that you received from the **{location}** pokestop. You can reply with **cancel** to stop anytime.").format(location=location), inline=False)
                    questwait = await channel.send(embed=research_embed)
                    try:
                        questmsg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        questmsg = None
                    await utils.safe_delete(questwait)
                    if not questmsg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(questmsg)
                    if questmsg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif questmsg:
                        quest = questmsg.clean_content
                    research_embed.set_field_at(0, name=research_embed.fields[0].name, value=_("Fantastic! Now, reply with the **reward** you earned for the **{quest}** quest that you received from the **{location}** pokestop. You can reply with **cancel** to stop anytime").format(quest=quest, location=location), inline=False)
                    rewardwait = await channel.send(embed=research_embed)
                    try:
                        rewardmsg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        rewardmsg = None
                    await utils.safe_delete(rewardwait)
                    if not rewardmsg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(rewardmsg)
                    if rewardmsg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif rewardmsg:
                        reward = rewardmsg.clean_content
                    break
        if not error:
            await self.send_research(ctx, location, quest, reward)
        else:
            research_embed.clear_fields()
            research_embed.add_field(name=_('**Research Report Cancelled**'), value=_("Meowth! Your report has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await channel.send(embed=research_embed, delete_after=10)
            if not message.embeds:
                await utils.safe_delete(message)

    async def make_research_embed(self, ctx, res_pokemon, poi_info, location, loc_url, quest, reward):
        timestamp = (ctx.message.created_at + datetime.timedelta(hours=self.bot.guild_dict[ctx.message.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        research_embed = discord.Embed(colour=ctx.guild.me.colour, url=loc_url).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/field-research.png?cache=1')
        research_embed.title = _('Meowth! Click here for my directions to the research!')
        research_embed.description = _("Ask {author} if my directions aren't perfect!").format(author=ctx.author.name)
        item = None
        if res_pokemon:
            research_embed.set_thumbnail(url=res_pokemon.img_url)
        else:
            thumbnail_url, item = await utils.get_item(reward)
            if item:
                research_embed.set_thumbnail(url=thumbnail_url)
        research_embed.add_field(name=_("**Pokestop:**"), value=f"{string.capwords(location, ' ')} {poi_info}", inline=True)
        research_embed.add_field(name=_("**Quest:**"), value=string.capwords(quest, " "), inline=True)
        research_embed.add_field(name=_("**Reward:**"), value=string.capwords(reward, " "), inline=True)
        research_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=ctx.author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=ctx.author.avatar_url_as(format=None, static_format='jpg', size=32))
        research_embed.set_author(name="Field Research Report", icon_url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/field-research.png?cache=1")
        return research_embed

    async def send_research(self, ctx, location, quest, reward):
        dm_dict = {}
        research_dict = self.bot.guild_dict[ctx.guild.id].setdefault('questreport_dict', {})
        timestamp = (ctx.message.created_at + datetime.timedelta(hours=self.bot.guild_dict[ctx.message.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        to_midnight = 24*60*60 - ((timestamp-timestamp.replace(hour=0, minute=0, second=0, microsecond=0)).seconds)
        complete_emoji = self.bot.custom_emoji.get('research_complete', u'\U00002705')
        expire_emoji = self.bot.custom_emoji.get('research_expired', u'\U0001F4A8')
        info_emoji = ctx.bot.custom_emoji.get('research_info', u'\U00002139\U0000fe0f')
        report_emoji = self.bot.custom_emoji.get('research_report', u'\U0001F4E2')
        list_emoji = ctx.bot.custom_emoji.get('list_emoji', u'\U0001f5d2\U0000fe0f')
        react_list = [complete_emoji, expire_emoji, info_emoji, report_emoji, list_emoji]
        pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, reward)
        reward_list = ["ball", "nanab", "pinap", "razz", "berr", "stardust", "potion", "revive", "candy", "lure", "module", "mysterious", "component", "radar", "sinnoh", "unova", "stone", "scale", "coat", "grade"]
        other_reward = any(x in reward.lower() for x in reward_list)
        research_msg = f"Meowth! Field Research reported by {ctx.author.mention}! Details: {location}\n\nUse {complete_emoji} if completed, {expire_emoji} if expired, {info_emoji} to edit details, {report_emoji} to report new, or {list_emoji} to list all research!"
        loc_url = utils.create_gmaps_query(self.bot, location, ctx.channel, type="research")
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        stop_info = ""
        if gym_matching_cog:
            stop_info, location, stop_url = await gym_matching_cog.get_poi_info(ctx, location, "research", dupe_check=False, autocorrect=False)
            if stop_url:
                loc_url = stop_url
        if not location:
            return
        item = None
        shiny_str = ""
        if pokemon and "research" in pokemon.shiny_available:
            shiny_str = self.bot.custom_emoji.get('shiny_chance', u'\U00002728') + " "
        if pokemon and not other_reward:
            reward = f"{shiny_str}{string.capwords(reward, ' ')} {pokemon.emoji}"
            pokemon.shiny = False
            pokemon.gender = False
            pokemon.size = False
            pokemon.shadow = False
        elif other_reward:
            pokemon = None
        research_embed = await self.make_research_embed(ctx, pokemon, stop_info, location, loc_url, quest, reward)
        if pokemon:
            reward = reward.replace(pokemon.emoji, "").replace(shiny_str, "").strip()
        else:
            __, item = await utils.get_item(reward)
        ctx.resreportmsg = await ctx.channel.send(research_msg, embed=research_embed)
        for reaction in react_list:
            await asyncio.sleep(0.25)
            await utils.add_reaction(ctx.resreportmsg, reaction)
        self.bot.guild_dict[ctx.guild.id]['questreport_dict'][ctx.resreportmsg.id] = {
            'exp':time.time() + to_midnight - 60,
            'expedit':"delete",
            'report_message':ctx.message.id,
            'report_channel':ctx.channel.id,
            'report_author':ctx.author.id,
            'report_guild':ctx.guild.id,
            'dm_dict':dm_dict,
            'location':location,
            'url':loc_url,
            'quest':quest,
            'reward':item if item else reward,
            'completed_by':[]
        }
        dm_dict = await self.send_dm_messages(ctx, pokemon, location, item, copy.deepcopy(research_embed), dm_dict)
        self.bot.guild_dict[ctx.guild.id]['questreport_dict'][ctx.resreportmsg.id]['dm_dict'] = dm_dict
        if not ctx.author.bot:
            research_reports = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('reports', {}).setdefault('research', 0) + 1
            self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['reports']['research'] = research_reports

    async def send_dm_messages(self, ctx, res_pokemon, location, item, embed, dm_dict):
        if embed:
            if isinstance(embed.description, discord.embeds._EmptyEmbed):
                embed.description = ""
            if "Jump to Message" not in embed.description:
                embed.description = embed.description + f"\n**Report:** [Jump to Message]({ctx.resreportmsg.jump_url})"
            index = 0
            for field in embed.fields:
                if "reaction" in field.name.lower():
                    embed.remove_field(index)
                else:
                    index += 1
        pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, res_pokemon)
        if pokemon:
            pkmn_types = pokemon.types.copy()
        else:
            pkmn_types = ['None']
        pkmn_types.append('None')
        for trainer in self.bot.guild_dict[ctx.guild.id].get('trainers', {}):
            user_wants = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('wants', [])
            user_forms = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('forms', [])
            pokemon_setting = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].get('alerts', {}).get('settings', {}).get('categories', {}).get('pokemon', {}).get('research', True)
            user_stops = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('stops', [])
            stop_setting = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].get('alerts', {}).get('settings', {}).get('categories', {}).get('pokestop', {}).get('research', True)
            user_items = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('items', [])
            item_setting = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].get('alerts', {}).get('settings', {}).get('categories', {}).get('item', {}).get('research', True)
            user_types = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('types', [])
            type_setting = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].get('alerts', {}).get('settings', {}).get('categories', {}).get('type', {}).get('research', True)
            if not any([user_wants, user_forms, pokemon_setting, user_stops, stop_setting, user_items, item_setting, user_types, type_setting]):
                continue
            if not checks.dm_check(ctx, trainer, "research") or trainer in dm_dict:
                continue
            send_research = []
            if pokemon_setting and pokemon and pokemon.id in user_wants:
                send_research.append(f"Pokemon: {pokemon.name.title()}")
            if pokemon_setting and pokemon and str(pokemon) in user_forms:
                send_research.append(f"Pokemon Form: {str(pokemon)}")
            if stop_setting and location.lower() in user_stops:
                send_research.append(f"Pokestop: {location.title()}")
            if item_setting and item in user_items:
                send_research.append(f"Item: {item.title()}")
            if type_setting and pkmn_types[0].lower() in user_types:
                type_emoji = utils.parse_emoji(ctx.guild, self.bot.config.type_id_dict[pkmn_types[0].lower()])
                send_research.append(f"Type: {type_emoji}")
            if type_setting and pkmn_types[1].lower() in user_types:
                type_emoji = utils.parse_emoji(ctx.guild, self.bot.config.type_id_dict[pkmn_types[1].lower()])
                send_research.append(f"Type: {type_emoji}")
            if send_research:
                embed.description = embed.description + f"\n**Subscription:** {(', ').join(send_research)}"
                try:
                    user = ctx.guild.get_member(trainer)
                    resdmmsg = await user.send(f"Meowth! {pokemon.name.title() + ' ' if pokemon else ''}Field Research reported by {ctx.author.display_name} in {ctx.channel.mention}! Details: {location}", embed=embed)
                    dm_dict[user.id] = resdmmsg.id
                except:
                    pass
                embed.description = embed.description.replace(f"\n**Subscription:** {(', ').join(send_research)}", "")
        return dm_dict

    @research.command(aliases=['expire'])
    @checks.allowresearchreport()
    @commands.has_permissions(manage_channels=True)
    async def reset(self, ctx, *, report_message=None):
        """Resets all research reports.

        Usage: !research reset [message]
        Will either reset [message] or all if no message is supplied"""
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel

        # get settings
        research_dict = copy.deepcopy(self.bot.guild_dict[guild.id].setdefault('questreport_dict', {}))
        reset_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/emoji/unicode_dash.png?cache=1')
        await utils.safe_delete(message)

        if not research_dict:
            return
        if report_message and int(report_message) in research_dict.keys():
            try:
                report_message = await channel.fetch_message(report_message)
            except:
                await utils.expire_dm_reports(self.bot, research_dict[report_message].get('dm_dict', {}))
                del self.bot.guild_dict[guild.id]['questreport_dict'][report_message]
                return
            await self.expire_research(report_message)
            return
        reset_embed.add_field(name=f"**Reset Research Reports**", value=f"**Meowth!** Are you sure you\'d like to remove all research reports?")
        rusure = await channel.send(embed=reset_embed)
        try:
            timeout = False
            res, reactuser = await utils.ask(self.bot, rusure, author.id)
        except TypeError:
            timeout = True
        if timeout or res.emoji == self.bot.custom_emoji.get('answer_no', u'\U0000274e'):
            await utils.safe_delete(rusure)
            reset_embed.clear_fields()
            reset_embed.add_field(name=f"Reset Cancelled", value=f"Your research reset request has been canceled. No changes have been made.")
            return await channel.send(embed=reset_embed, delete_after=10)
        elif res.emoji == self.bot.custom_emoji.get('answer_yes', u'\U00002705'):
            await utils.safe_delete(rusure)
            async with ctx.typing():
                for report in research_dict:
                    try:
                        report_message = await channel.fetch_message(report)
                    except:
                        await utils.expire_dm_reports(self.bot, research_dict[report].get('dm_dict', {}))
                        del self.bot.guild_dict[guild.id]['questreport_dict'][report]
                        return
                    self.bot.loop.create_task(self.expire_research(report_message))
                reset_embed.clear_fields()
                reset_embed.add_field(name=f"Research Reset", value=f"Your reset request has been completed.")
                return await channel.send(embed=reset_embed, delete_after=10)
        else:
            return

def setup(bot):
    bot.add_cog(Research(bot))

def teardown(bot):
    bot.remove_cog(Research)
