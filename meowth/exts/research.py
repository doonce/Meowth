import asyncio
import copy
import re
import time
import datetime
import dateparser
import textwrap
import logging
import string

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

    def cog_unload(self):
        self.research_cleanup.cancel()

    @tasks.loop(seconds=0)
    async def research_cleanup(self, loop=True):
        logger.info('------ BEGIN ------')
        guilddict_temp = copy.deepcopy(self.bot.guild_dict)
        midnight_list = []
        count = 0
        for guildid in guilddict_temp.keys():
            utcnow = (datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[guildid]['configure_dict']['settings']['offset']))
            to_midnight = 24*60*60 - ((utcnow-utcnow.replace(hour=0, minute=0, second=0, microsecond=0)).seconds)
            midnight_list.append(to_midnight)
            research_dict = guilddict_temp[guildid].setdefault('questreport_dict', {})
            for reportid in research_dict.keys():
                if research_dict[reportid].get('exp', 0) <= time.time():
                    report_channel = self.bot.get_channel(research_dict[reportid].get('report_channel'))
                    if report_channel:
                        try:
                            report_message = await report_channel.fetch_message(reportid)
                            self.bot.loop.create_task(self.expire_research(report_message))
                            count += 1
                            continue
                        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                            pass
                    try:
                        del self.bot.guild_dict[guildid]['questreport_dict'][reportid]
                    except KeyError:
                        pass
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
        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.errors.NotFound, AttributeError, discord.Forbidden):
            return
        guild = message.guild
        try:
            user = guild.get_member(payload.user_id)
        except AttributeError:
            return
        guild = message.guild
        can_manage = channel.permissions_for(user).manage_messages
        try:
            research_dict = self.bot.guild_dict[guild.id]['questreport_dict']
        except KeyError:
            research_dict = {}
        if message.id in research_dict and user.id != self.bot.user.id:
            research_dict =  self.bot.guild_dict[guild.id]['questreport_dict'][message.id]
            if str(payload.emoji) == self.bot.custom_emoji.get('research_complete', '\u2705'):
                if user.id not in research_dict.get('completed_by', []):
                    if user.id != research_dict['report_author']:
                        research_dict.get('completed_by', []).append(user.id)
            elif str(payload.emoji) == self.bot.custom_emoji.get('research_expired', '\U0001F4A8'):
                for reaction in message.reactions:
                    if reaction.emoji == self.bot.custom_emoji.get('research_expired', '\U0001F4A8') and (reaction.count >= 3 or can_manage):
                        await self.expire_research(message)

    async def expire_research(self, message):
        guild = message.channel.guild
        channel = message.channel
        research_dict = copy.deepcopy(self.bot.guild_dict[guild.id]['questreport_dict'])
        await utils.safe_delete(message)
        try:
            user_message = await channel.fetch_message(research_dict[message.id]['report_message'])
            await utils.safe_delete(user_message)
        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException, KeyError):
            pass
        await utils.expire_dm_reports(self.bot, research_dict[message.id].get('dm_dict', {}))
        research_bonus = research_dict.get(message.id, {}).get('completed_by', [])
        if len(research_bonus) >= 3 and not message.author.bot:
            research_reports = self.bot.guild_dict[message.guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('research_reports', 0) + 1
            self.bot.guild_dict[message.guild.id]['trainers'][message.author.id]['research_reports'] = research_reports
        try:
            del self.bot.guild_dict[guild.id]['questreport_dict'][message.id]
        except KeyError:
            pass

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
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset']))
        error = False
        loc_url = utils.create_gmaps_query(self.bot, "", message.channel, type="research")
        research_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/field-research.png?cache=1')
        research_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        pokemon = False
        reward_list = ["ball", "nanab", "pinap", "razz", "berr", "stardust", "potion", "revive", "candy", "lure", "module"]
        research_dict = self.bot.guild_dict[ctx.guild.id].setdefault('questreport_dict', {})
        while True:
            async with ctx.typing():
                if details:
                    research_split = details.rsplit(",", 2)
                    if len(research_split) != 3:
                        error = _("entered an incorrect amount of arguments.\n\nUsage: **!research** or **!research <pokestop>, <quest>, <reward>**")
                        break
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
                    research_embed.add_field(name=_("**Pokestop:**"), value=f"{string.capwords(location, ' ')} {stop_info}", inline=True)
                    research_embed.add_field(name=_("**Quest:**"), value=string.capwords(quest, " "), inline=True)
                    other_reward = any(x in reward.lower() for x in reward_list)
                    shiny_str = ""
                    pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, reward, allow_digits=False)
                    if pokemon and pokemon.id in self.bot.shiny_dict:
                        if pokemon.alolan and "alolan" in self.bot.shiny_dict.get(pokemon.id, {}) and "research" in self.bot.shiny_dict.get(pokemon.id, {}).get("alolan", []):
                            shiny_str = self.bot.custom_emoji.get('shiny_chance', '\u2728') + " "
                        elif str(pokemon.form).lower() in self.bot.shiny_dict.get(pokemon.id, {}) and "research" in self.bot.shiny_dict.get(pokemon.id, {}).get(str(pokemon.form).lower(), []):
                            shiny_str = self.bot.custom_emoji.get('shiny_chance', '\u2728') + " "
                    if pokemon and not other_reward:
                        reward = f"{shiny_str}{string.capwords(reward, ' ')} {pokemon.emoji}"
                        research_embed.add_field(name=_("**Reward:**"), value=reward, inline=True)
                        reward = reward.replace(pokemon.emoji, "").replace(shiny_str, "").strip()
                    else:
                        research_embed.add_field(name=_("**Reward:**"), value=string.capwords(reward, " "), inline=True)
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
                        research_embed.add_field(name=_("**Pokestop:**"), value=f"{string.capwords(location, ' ')} {stop_info}", inline=True)
                        research_embed.add_field(name=_("**Quest:**"), value=string.capwords(quest, " "), inline=True)
                        reward = rewardmsg.clean_content
                        other_reward = any(x in reward.lower() for x in reward_list)
                        shiny_str = ""
                        pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, reward, allow_digits=False)
                        if pokemon and not other_reward:
                            if pokemon.id in self.bot.shiny_dict:
                                if pokemon.alolan and "alolan" in self.bot.shiny_dict.get(pokemon.id, {}) and "wild" in self.bot.shiny_dict.get(pokemon.id, {}).get("alolan", []):
                                    shiny_str = self.bot.custom_emoji.get('shiny_chance', '\u2728') + " "
                                elif str(pokemon.form).lower() in self.bot.shiny_dict.get(pokemon.id, {}) and "wild" in self.bot.shiny_dict.get(pokemon.id, {}).get(str(pokemon.form).lower(), []):
                                    shiny_str = self.bot.custom_emoji.get('shiny_chance', '\u2728') + " "
                            reward = f"{shiny_str}{string.capwords(reward, ' ')} {pokemon.emoji}"
                            research_embed.add_field(name=_("**Reward:**"), value=string.capwords(reward, ' '), inline=True)
                            reward = reward.replace(pokemon.emoji, "").replace(shiny_str, "").strip()
                        else:
                            research_embed.add_field(name=_("**Reward:**"), value=string.capwords(reward, " "), inline=True)
                    research_embed.remove_field(0)
                    break
        if not error:
            await self.send_research(ctx, research_embed, location, quest, reward, other_reward, loc_url)
        else:
            research_embed.clear_fields()
            research_embed.add_field(name=_('**Research Report Cancelled**'), value=_("Meowth! Your report has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await channel.send(embed=research_embed, delete_after=10)
            await utils.safe_delete(message)

    async def send_research(self, ctx, research_embed, location, quest, reward, other_reward, loc_url):
        dm_dict = {}
        timestamp = (ctx.message.created_at + datetime.timedelta(hours=self.bot.guild_dict[ctx.message.channel.guild.id]['configure_dict']['settings']['offset']))
        to_midnight = 24*60*60 - ((timestamp-timestamp.replace(hour=0, minute=0, second=0, microsecond=0)).seconds)
        pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, reward, allow_digits=False)
        dust = re.search(r'(?i)dust', reward)
        candy = re.search(r'(?i)candy|(?i)candies', reward)
        pinap = re.search(r'(?i)pinap', reward)
        silverpinap = re.search(r'(?i)silver pinap', reward)
        razz = re.search(r'(?i)razz', reward)
        goldenrazz = re.search(r'(?i)golde?n? razz', reward)
        nanab = re.search(r'(?i)nanab', reward)
        lure = re.search(r'(?i)lure', reward)
        glaciallure = re.search(r'(?i)glacial lure', reward)
        magnetlure = re.search(r'(?i)magnetic lure', reward)
        mossylure = re.search(r'(?i)mossy lure', reward)
        pokeball = re.search(r'(?i)ball', reward)
        greatball = re.search(r'(?i)great ball', reward)
        ultraball = re.search(r'(?i)ultra ball', reward)
        potion = re.search(r'(?i)potion', reward)
        superpotion = re.search(r'(?i)super potion', reward)
        hyperpotion = re.search(r'(?i)hyper potion', reward)
        maxpotion = re.search(r'(?i)max potion', reward)
        revive = re.search(r'(?i)revive', reward)
        maxrevive = re.search(r'(?i)max revive', reward)
        fasttm = re.search(r'(?i)fast tm', reward)
        chargetm = re.search(r'(?i)charged? tm', reward)
        starpiece = re.search(r'(?i)star piece', reward)
        research_msg = _("Field Research reported by {author}").format(author=ctx.author.mention)
        research_embed.title = _('Meowth! Click here for my directions to the research!')
        research_embed.description = _("Ask {author} if my directions aren't perfect!").format(author=ctx.author.name)
        research_embed.url = loc_url
        item = None
        pkmn_types = ["None", "None"]
        if pokemon and not other_reward:
            research_embed.set_thumbnail(url=pokemon.img_url)
            pkmn_types = copy.deepcopy(pokemon.types)
            pkmn_types.append('None')
        elif dust:
            research_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/stardust_painted.png")
            item = "stardust"
        elif candy:
            research_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/Item_1301.png")
            item = "rare candy"
        elif pinap and not silverpinap:
            research_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/Item_0705.png")
            item = "pinap berry"
        elif pinap and silverpinap:
            research_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/Item_0707.png")
            item = "silver pinap berry"
        elif razz and not goldenrazz:
            research_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/Item_0701.png")
            item = "razz berry"
        elif razz and goldenrazz:
            research_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/Item_0706.png")
            item = "golden razz berry"
        elif nanab:
            research_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/Item_0703.png")
            item = "nanab berry"
        elif pokeball and not ultraball and not greatball:
            research_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/Item_0001.png")
            item = "poke ball"
        elif pokeball and greatball:
            research_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/Item_0002.png")
            item = "great ball"
        elif pokeball and ultraball:
            research_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/Item_0003.png")
            item = "ultra ball"
        elif potion and not superpotion and not hyperpotion and not maxpotion:
            research_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/Item_0101.png")
            item = "potion"
        elif potion and superpotion:
            research_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/Item_0102.png")
            item = "super potion"
        elif potion and hyperpotion:
            research_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/Item_0103.png")
            item = "hyper potion"
        elif potion and maxpotion:
            research_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/Item_0104.png")
            item = "max potion"
        elif revive and not maxrevive:
            research_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/Item_0201.png")
            item = "revive"
        elif revive and maxrevive:
            research_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/Item_0202.png")
            item = "max revive"
        elif fasttm:
            research_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/Item_1201.png")
            item = "fast tm"
        elif chargetm:
            research_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/Item_1202.png")
            item = "charged tm"
        elif starpiece:
            research_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/starpiece.png")
            item = "star piece"
        elif lure and not glaciallure and not magnetlure and not mossylure:
            research_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey.png")
            item = "lure module"
        elif lure and glaciallure:
            research_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey_glacial.png")
            item = "glacial lure module"
        elif lure and magnetlure:
            research_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey_magnetic.png")
            item = "magnetic lure module"
        elif lure and mossylure:
            research_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey_mossy.png")
            item = "mossy lure module"
        research_embed.set_author(name="Field Research Report", icon_url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/field-research.png?cache=1")
        confirmation = await ctx.channel.send(research_msg, embed=research_embed)
        await utils.safe_reaction(confirmation, self.bot.custom_emoji.get('research_complete', '\u2705'))
        await utils.safe_reaction(confirmation, self.bot.custom_emoji.get('research_expired', '\ud83d\udca8'))
        self.bot.guild_dict[ctx.guild.id]['questreport_dict'][confirmation.id] = {
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
            'reward':reward,
            'completed_by':[]
        }
        if not ctx.author.bot:
            research_reports = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('research_reports', 0) + 1
            self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['research_reports'] = research_reports

        research_embed.description = research_embed.description + f"\n**Report:** [Jump to Message]({confirmation.jump_url})"
        for trainer in self.bot.guild_dict[ctx.guild.id].get('trainers', {}):
            user_wants = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('wants', [])
            user_stops = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('stops', [])
            user_items = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('items', [])
            user_types = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('types', [])
            if not checks.dm_check(ctx, trainer):
                continue
            if (pokemon and pokemon.id in user_wants) or location.lower() in user_stops or item in user_items or pkmn_types[0].lower() in user_types or pkmn_types[1].lower() in user_types:
                try:
                    user = ctx.guild.get_member(trainer)
                    if pokemon:
                        resdmmsg = await user.send(_("{pkmn} Field Research reported by {author} in {channel}").format(pkmn=string.capwords(pokemon.name, ' '), author=ctx.author.display_name, channel=ctx.channel.mention), embed=research_embed)
                    else:
                        resdmmsg = await user.send(_("Field Research reported by {author} in {channel}").format(author=ctx.author.display_name, channel=ctx.channel.mention), embed=research_embed)
                    dm_dict[user.id] = resdmmsg.id
                except:
                    continue
        self.bot.guild_dict[ctx.guild.id]['questreport_dict'][confirmation.id]['dm_dict'] = dm_dict

    @research.command(aliases=['expire'])
    @checks.allowresearchreport()
    @commands.has_permissions(manage_channels=True)
    async def reset(self, ctx, *, report_message=None):
        """Resets all research reports."""
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel

        # get settings
        research_dict = copy.deepcopy(self.bot.guild_dict[guild.id].setdefault('questreport_dict', {}))
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
        rusure = await channel.send(_('**Meowth!** Are you sure you\'d like to remove all research reports?'))
        try:
            timeout = False
            res, reactuser = await utils.ask(self.bot, rusure, author.id)
        except TypeError:
            timeout = True
        if timeout or res.emoji == self.bot.custom_emoji.get('answer_no', '\u274e'):
            await utils.safe_delete(rusure)
            confirmation = await channel.send(_('Manual reset cancelled.'), delete_after=10)
            return
        elif res.emoji == self.bot.custom_emoji.get('answer_yes', '\u2705'):
            await utils.safe_delete(rusure)
            for report in research_dict:
                try:
                    report_message = await channel.fetch_message(report)
                except:
                    await utils.expire_dm_reports(self.bot, research_dict[report].get('dm_dict', {}))
                    del self.bot.guild_dict[guild.id]['questreport_dict'][report]
                    return
                self.bot.loop.create_task(self.expire_research(report_message))
            confirmation = await channel.send(_('Research reset.'), delete_after=10)
            return
        else:
            return

def setup(bot):
    bot.add_cog(Research(bot))

def teardown(bot):
    bot.remove_cog(Research)
