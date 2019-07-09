
import asyncio
import re
from aiohttp import ClientSession
import os
import functools
import textwrap
import datetime
import copy
import logging
import aiohttp

from dateutil.relativedelta import relativedelta

from fuzzywuzzy import fuzz
from fuzzywuzzy import process

import discord
from discord.ext import commands, tasks

from meowth import checks
from meowth.exts import pokemon as pkmn_class

logger = logging.getLogger("meowth")

def get_match(word_list: list, word: str, score_cutoff: int = 60):
    """Uses fuzzywuzzy to see if word is close to entries in word_list

    Returns a tuple of (MATCH, SCORE)
    """
    if not word:
        return (None, None)
    result = process.extractOne(
        word, word_list, scorer=fuzz.ratio, score_cutoff=score_cutoff)
    if not result:
        return (None, None)
    return result

def colour(*args):
    """Returns a discord Colour object.

    Pass one as an argument to define colour:
        `int` match colour value.
        `str` match common colour names.
        `discord.Guild` bot's guild colour.
        `None` light grey.
    """
    arg = args[0] if args else None
    if isinstance(arg, int):
        return discord.Colour(arg)
    if isinstance(arg, str):
        colour = arg
        try:
            return getattr(discord.Colour, colour)()
        except AttributeError:
            return discord.Colour.lighter_grey()
    if isinstance(arg, discord.Guild):
        return arg.me.colour
    else:
        return discord.Colour.lighter_grey()

def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False

def make_embed(msg_type='', title=None, icon=None, content=None,
               msg_colour=None, guild=None, title_url=None,
               thumbnail='', image='', fields=None, footer=None,
               footer_icon=None, inline=False):
    """Returns a formatted discord embed object.

    Define either a type or a colour.
    Types are:
    error, warning, info, success, help.
    """

    embed_types = {
        'error':{
            'icon':'https://i.imgur.com/juhq2uJ.png',
            'colour':'red'
        },
        'warning':{
            'icon':'https://i.imgur.com/4JuaNt9.png',
            'colour':'gold'
        },
        'info':{
            'icon':'https://i.imgur.com/wzryVaS.png',
            'colour':'blue'
        },
        'success':{
            'icon':'https://i.imgur.com/ZTKc3mr.png',
            'colour':'green'
        },
        'help':{
            'icon':'https://i.imgur.com/kTTIZzR.png',
            'colour':'blue'
        }
    }
    if msg_type in embed_types.keys():
        msg_colour = embed_types[msg_type]['colour']
        icon = embed_types[msg_type]['icon']
    if guild and not msg_colour:
        msg_colour = colour(guild)
    else:
        if not isinstance(msg_colour, discord.Colour):
            msg_colour = colour(msg_colour)
    embed = discord.Embed(description=content, colour=msg_colour)
    if not title_url:
        title_url = discord.Embed.Empty
    if not icon:
        icon = discord.Embed.Empty
    if title:
        embed.set_author(name=title, icon_url=icon, url=title_url)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    if image:
        embed.set_image(url=image)
    if fields:
        for key, value in fields.items():
            ilf = inline
            if not isinstance(value, str):
                ilf = value[0]
                value = value[1]
            embed.add_field(name=key, value=value, inline=ilf)
    if footer:
        footer = {'text':footer}
        if footer_icon:
            footer['icon_url'] = footer_icon
        embed.set_footer(**footer)
    return embed

def bold(msg: str):
    """Format to bold markdown text"""
    return f'**{msg}**'

def italics(msg: str):
    """Format to italics markdown text"""
    return f'*{msg}*'

def bolditalics(msg: str):
    """Format to bold italics markdown text"""
    return f'***{msg}***'

def code(msg: str):
    """Format to markdown code block"""
    return f'```{msg}```'

def pycode(msg: str):
    """Format to code block with python code highlighting"""
    return f'```py\n{msg}```'

def ilcode(msg: str):
    """Format to inline markdown code"""
    return f'`{msg}`'

def convert_to_bool(argument):
    lowered = argument.lower()
    if lowered in ('yes', 'y', 'true', 't', '1', 'enable', 'on'):
        return True
    elif lowered in ('no', 'n', 'false', 'f', '0', 'disable', 'off'):
        return False
    else:
        return None

def sanitize_channel_name(name):
    """Converts a given string into a compatible discord channel name."""
    # Remove all characters other than alphanumerics,
    # dashes, underscores, and spaces
    ret = re.sub('[^a-zA-Z0-9 _\\-]', '', name)
    # Replace spaces with dashes
    ret = ret.replace(' ', '-')
    return ret

async def get_raid_help(prefix, avatar, user=None):
    helpembed = discord.Embed(colour=discord.Colour.lighter_grey())
    helpembed.set_author(name="Raid Coordination Help", icon_url=avatar)
    helpembed.add_field(
        name="Key",
        value="<> denote required arguments, [] denote optional arguments",
        inline=False)
    helpembed.add_field(
        name="Raid MGMT Commands",
        value=(
            f"`{prefix}raid <species>`\n"
            f"`{prefix}weather <weather>`\n"
            f"`{prefix}timerset <minutes>`\n"
            f"`{prefix}starttime <time>`\n"
            "`<google maps link>`\n"
            "**RSVP**\n"
            f"`{prefix}i, {prefix}c, {prefix}h, {prefix}x...\n"
            "[total]...\n"
            "[team counts]`\n"
            "**Lists**\n"
            f"`{prefix}list [status]`\n"
            f"`{prefix}list [status] tags`\n"
            f"`{prefix}list teams`\n\n"
            f"`{prefix}starting [team]`"))
    helpembed.add_field(
        name="Description",
        value=(
            "`Hatches Egg channel`\n"
            "`Sets in-game weather`\n"
            "`Sets hatch/raid timer`\n"
            "`Sets start time`\n"
            "`Updates raid location`\n\n"
            "`interested, coming, here, cancel`\n"
            "`# of trainers`\n"
            "`# from each team (ex. 3m for 3 Mystic)`\n\n"
            "`Lists trainers by status`\n"
            "`@mentions trainers by status`\n"
            "`Lists trainers by team`\n\n"
            "`Moves trainers on 'here' list to a lobby.`"))
    helpembed.add_field(
        name="README",
        value="Visit our [README](https://github.com/doonce/meowth#directions-for-using-meowth) for a full list of commands.",
        inline=False)
    if not user:
        return helpembed
    await user.send(embed=helpembed)

def get_number(bot, pkmn_name):
    pkmn_name = pkmn_name.lower()
    try:
        number = bot.pkmn_info[pkmn_name]['number']
    except:
        number = None
    return number

def get_name(bot, pkmn_number):
    pkmn_number = int(pkmn_number)
    try:
        name = bot.pkmn_list[pkmn_number-1]
    except:
        name = None
    return name

async def get_raidlist(bot):
    raid_tuple = ()
    for level in bot.raid_info['raid_eggs']:
        for pkmn in bot.raid_info['raid_eggs'][level]['pokemon']:
            pkmn_tuple = ()
            pokemon = await pkmn_class.Pokemon.async_get_pokemon(bot, pkmn)
            pkmn_tuple = (pokemon, str(pokemon), pokemon.name, pokemon.id)
            raid_tuple = (*pkmn_tuple, *raid_tuple)
    return raid_tuple

def get_level(bot, pkmn):
    entered_pkmn = pkmn_class.Pokemon.get_pokemon(bot, pkmn)
    for level in bot.raid_info['raid_eggs']:
        for level, pkmn_list in bot.raid_info['raid_eggs'].items():
            for pokemon in pkmn_list['pokemon']:
                pokemon = pkmn_class.Pokemon.get_pokemon(bot, pokemon)
                if pokemon and entered_pkmn and pokemon.id == entered_pkmn.id:
                    return level

async def ask(bot, message, user_list=None, timeout=60, *, react_list=[]):
    if not react_list:
        react_list=[bot.custom_emoji.get('answer_yes', '\u2705'), bot.custom_emoji.get('answer_no', '\u274e')]
    if user_list and type(user_list) != list:
        user_list = [user_list]
    def check(reaction, user):
        if user_list and type(user_list) is list:
            return (user.id in user_list) and (reaction.message.id == message.id) and (reaction.emoji in react_list)
        elif not user_list:
            return (user.id != message.author.id) and (reaction.message.id == message.id) and (reaction.emoji in react_list)
    for r in react_list:
        await asyncio.sleep(0.25)
        await safe_reaction(message, r)
    try:
        reaction, user = await bot.wait_for('reaction_add', check=check, timeout=timeout)
        return reaction, user
    except asyncio.TimeoutError:
        await message.clear_reactions()
        return

async def letter_case(iterable, find, *, limits=None):
    servercase_list = []
    lowercase_list = []
    for item in iterable:
        if not item.name:
            continue
        elif item.name and (not limits or item.name.lower() in limits):
            servercase_list.append(item.name)
            lowercase_list.append(item.name.lower())
    if find.lower() in lowercase_list:
        index = lowercase_list.index(find.lower())
        return servercase_list[index]
    else:
        return None

def do_template(message, author, guild):
    not_found = []

    def template_replace(match):
        if match.group(3):
            if match.group(3) == 'user':
                return '{user}'
            elif match.group(3) == 'server':
                return guild.name
            else:
                return match.group(0)
        if match.group(4):
            emoji = (':' + match.group(4)) + ':'
            return parse_emoji(guild, emoji)
        match_type = match.group(1)
        full_match = match.group(0)
        match = match.group(2)
        if match_type == '<':
            mention_match = re.search('(#|@!?|&)([0-9]+)', match)
            match_type = mention_match.group(1)[0]
            match = mention_match.group(2)
        if match_type == '@':
            member = guild.get_member_named(match)
            if match.isdigit() and (not member):
                member = guild.get_member(int(match))
            if (not member):
                not_found.append(full_match)
            return member.mention if member else full_match
        elif match_type == '#':
            channel = discord.utils.get(guild.text_channels, name=match)
            if match.isdigit() and (not channel):
                channel = guild.get_channel(int(match))
            if (not channel):
                not_found.append(full_match)
            return channel.mention if channel else full_match
        elif match_type == '&':
            role = discord.utils.get(guild.roles, name=match)
            if match.isdigit() and (not role):
                role = discord.utils.get(guild.roles, id=int(match))
            if (not role):
                not_found.append(full_match)
            return role.mention if role else full_match
    template_pattern = '(?i){(@|#|&|<)([^{}]+)}|{(user|server)}|<*:([a-zA-Z0-9]+):[0-9]*>*'
    msg = re.sub(template_pattern, template_replace, message)
    return (msg, not_found)

async def autocorrect(bot, entered_word, word_list, destination, author):
    msg = _("Meowth! **{word}** isn't a Pokemon!").format(word=entered_word.title())
    match, score = get_match(word_list, entered_word)
    if match:
        msg += _(' Did you mean **{correction}**?').format(correction=match.title())
        question = await destination.send(msg)
        if author:
            try:
                timeout = False
                res, reactuser = await ask(bot, question, author.id)
            except TypeError:
                timeout = True
            await safe_delete(question)
            if timeout or res.emoji == bot.custom_emoji.get('answer_no', '\u274e'):
                return None
            elif res.emoji == bot.custom_emoji.get('answer_yes', '\u2705'):
                return match
            else:
                return None
        else:
            return None
    else:
        question = await destination.send(msg)
        return None

def parse_emoji(guild, emoji_string):
    if (emoji_string[0] == ':') and (emoji_string[(- 1)] == ':'):
        emoji = discord.utils.get(guild.emojis, name=emoji_string.strip(':'))
        if emoji:
            emoji_string = '<:{0}:{1}>'.format(emoji.name, emoji.id)
    return emoji_string

def print_emoji_name(guild, emoji_string):
    # By default, just print the emoji_string
    ret = ('`' + emoji_string) + '`'
    emoji = parse_emoji(guild, emoji_string)
    # If the string was transformed by the utils.parse_emoji
    # call, then it really was an emoji and we should
    # add the raw string so people know what to write.
    if emoji != emoji_string:
        ret = ((emoji + ' (`') + emoji_string) + '`)'
    return ret

def get_weaknesses(bot, species, form="none", alolan=False):
    # Get the Pokemon's number
    number = bot.pkmn_list.index(species)
    if not form:
        form = "none"
    if alolan:
        form = "alolan"
    # Look up its type
    try:
        pk_type = bot.pkmn_info[species]['forms'][form]['type']
    except KeyError:
        pk_type = bot.pkmn_info[species]['forms']["none"]['type']

    # Calculate sum of its weaknesses
    # and resistances.
    # -2 == immune
    # -1 == NVE
    #  0 == neutral
    #  1 == SE
    #  2 == double SE
    type_eff = {}
    for type in pk_type:
        for atk_type in bot.type_chart[type]:
            if atk_type not in type_eff:
                type_eff[atk_type] = 0
            type_eff[atk_type] += bot.type_chart[type][atk_type]
    ret = []
    for (type, effectiveness) in sorted(type_eff.items(), key=(lambda x: x[1]), reverse=True):
        if effectiveness == 1:
            ret.append(type.lower())
        elif effectiveness == 2:
            ret.append(type.lower() + 'x2')
    return ret

def weakness_to_str(bot, guild, weak_list):
    ret = ''
    for weakness in weak_list:

        x2 = ''
        if weakness[(- 2):] == 'x2':
            weakness = weakness[:(- 2)]
            x2 = 'x2'
        # Append to string
        ret += (parse_emoji(guild,
                bot.config.type_id_dict[weakness]) + x2) + ' '
    return ret

def create_gmaps_query(bot, details, channel, type="raid"):
    if type == "raid" or type == "egg":
        report = "raid"
    else:
        report = type
    if "/maps" in details and "http" in details:
        mapsindex = details.find('/maps')
        newlocindex = details.rfind('http', 0, mapsindex)
        if newlocindex == (- 1):
            return
        newlocend = details.find(' ', newlocindex)
        if newlocend == (- 1):
            newloc = details[newlocindex:]
            return newloc
        else:
            newloc = details[newlocindex:newlocend + 1]
            return newloc
    details_list = details.split()
    #look for lat/long coordinates in the location details. If provided,
    #then channel location hints are not needed in the  maps query
    if re.match(r'^\s*-?\d{1,2}\.?\d*,\s*-?\d{1,3}\.?\d*\s*$', details): #regex looks for lat/long in the format similar to 42.434546, -83.985195.
        return "https://www.google.com/maps/search/?api=1&query={0}".format('+'.join(details_list))
    loc_list = bot.guild_dict[channel.guild.id]['configure_dict'][report]['report_channels'].get(channel.id, "").split()
    return 'https://www.google.com/maps/search/?api=1&query={0}+{1}'.format('+'.join(details_list), '+'.join(loc_list))

def get_category(bot, channel, level, category_type="raid"):
    guild = channel.guild
    if category_type == "raid" or category_type == "egg":
        report = "raid"
    else:
        report = category_type
    catsort = bot.guild_dict[guild.id]['configure_dict'][report].get('categories', None)
    if catsort == "same":
        return channel.category
    elif catsort == "region":
        category = discord.utils.get(guild.categories, id=bot.guild_dict[guild.id]['configure_dict'][report]['category_dict'][channel.id])
        return category
    elif catsort == "level":
        category = discord.utils.get(guild.categories, id=bot.guild_dict[guild.id]['configure_dict'][report]['category_dict'][level])
        return category
    else:
        return None

async def get_report_dict(bot, channel):
    for report_dict in bot.channel_report_dicts:
        if hasattr(channel, "guild"):
            if channel and channel.id in bot.guild_dict[channel.guild.id].setdefault(report_dict, {}):
                return report_dict

async def get_object(ctx, snowflake, return_type="object"):
    iterables = [ctx.guild.text_channels, ctx.guild.categories, ctx.guild.roles, ctx.guild.members, ctx.bot.guilds]
    object = None
    for iterable in iterables:
        object = discord.utils.get(iterable, id=int(snowflake))
        if object:
            break
    if not object:
        return snowflake
    if return_type == "name":
        return object.name
    elif return_type == "mention":
        return object.mention
    elif return_type == "id":
        return object.id
    else:
        return object

async def expire_dm_reports(bot, dm_dict):
    for dm_user, dm_message in dm_dict.items():
        try:
            dm_user = bot.get_user(dm_user)
            if not dm_user:
                continue
            dm_channel = dm_user.dm_channel
            if not dm_channel:
                dm_channel = await dm_user.create_dm()
            if not dm_channel:
                continue
            dm_message = await dm_channel.fetch_message(dm_message)
            await dm_message.delete()
        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
            pass

async def safe_delete(message):
    try:
        await message.delete()
    except (discord.errors.Forbidden, discord.errors.HTTPException, discord.errors.NotFound, AttributeError):
        pass

async def safe_bulk_delete(channel, message_list):
    try:
        await channel.delete_messages(message_list)
    except (discord.errors.Forbidden, discord.errors.HTTPException, discord.errors.ClientException, AttributeError):
        pass

async def safe_reaction(message, reaction):
    try:
        await message.add_reaction(reaction)
    except (discord.errors.Forbidden, discord.errors.HTTPException, discord.errors.NotFound, discord.errors.InvalidArgument, AttributeError):
        pass

class Utilities(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.dm_cleanup.start()

    def cog_unload(self):
        self.dm_cleanup.cancel()

    @tasks.loop(seconds=0)
    async def dm_cleanup(self, loop=True):
        await self.dm_cleanup_func(loop)

    async def dm_cleanup_func(self, loop=True):
        if loop:
            await asyncio.sleep(302400)
        logger.info('------ BEGIN ------')
        guilddict_temp = copy.deepcopy(self.bot.guild_dict)
        count = 0
        def build_dm_list(guildid):
            global_dm_list = []
            for channel in guilddict_temp[guildid].get('nest_dict', {}):
                for nest in guilddict_temp[guildid]['nest_dict'][channel]:
                    if nest == "list":
                        continue
                    for report in guilddict_temp[guildid]['nest_dict'][channel][nest]['reports']:
                        for k,v in guilddict_temp[guildid]['nest_dict'][channel][nest]['reports'][report]['dm_dict'].items():
                            global_dm_list.append(v)
            for listing_id in guilddict_temp[guildid].get('trade_dict', {}):
                if guilddict_temp[guildid]['trade_dict'][listing_id].get('offers', {}):
                    for offer in guilddict_temp[guildid]['trade_dict'][listing_id].get('offers', {}):
                        global_dm_list.append(guilddict_temp[guildid]['trade_dict'][listing_id]['offers'][offer]['lister_msg'])
                if guilddict_temp[guildid]['trade_dict'][listing_id].get('active_check', 0):
                    global_dm_list.append(guilddict_temp[guildid]['trade_dict'][listing_id]['active_check'])
                if guilddict_temp[guildid]['trade_dict'][listing_id].get('accepted', {}):
                    global_dm_list.append(guilddict_temp[guildid]['trade_dict'][listing_id]['accepted']['lister_msg'])
                    global_dm_list.append(guilddict_temp[guildid]['trade_dict'][listing_id]['accepted']['buyer_msg'])
            report_list = ["questreport_dict", "wildreport_dict", "pokealarm_dict", "pokehuntr_dict", "raidchannel_dict", "lure_dict"]
            for report_dict in report_list:
                for report in guilddict_temp[guildid].get(report_dict, {}):
                    for k,v in guilddict_temp[guildid][report_dict][report].get('dm_dict', {}).items():
                        global_dm_list.append(v)
            return global_dm_list
        for guildid in guilddict_temp.keys():
            dm_list = build_dm_list(guildid)
            if not dm_list:
                continue
            delete_list = []
            trainers = guilddict_temp[guildid].get('trainers', {}).keys()
            for trainer in trainers:
                user = self.bot.get_user(trainer)
                if not user or user == self.bot.user:
                    continue
                dm_channel = user.dm_channel
                if not dm_channel:
                    try:
                        dm_channel = await user.create_dm()
                    except:
                        continue
                if not dm_channel:
                    continue
                async for message in user.dm_channel.history(limit=500):
                    if message.author.id == self.bot.user.id:
                        if "reported by" in message.content or "hatched into" in message.content or "reported that" in message.content:
                            if message.id not in dm_list:
                                delete_list.append(message)
                        elif "trade" in message.content.lower() or "offer" in message.content.lower():
                            if message.id not in dm_list:
                                if (datetime.datetime.now() - message.created_at).days >= 7:
                                    delete_list.append(message)
                        elif "welcome" in message.content.lower():
                            if (datetime.datetime.now() - message.created_at).days >= 30:
                                delete_list.append(message)
                        elif message.embeds:
                            if "pokebattler.com" in str(message.embeds[0].author.url).lower() or "raid coordination help" in str(message.embeds[0].author.name).lower():
                                if (datetime.datetime.now() - message.created_at).days >= 7:
                                    delete_list.append(message)
            dm_list = build_dm_list(guildid)
            for message in delete_list:
                if message.id not in dm_list:
                    try:
                        await message.delete()
                        count += 1
                    except:
                        continue
        logger.info(f"------ END - {count} DMs Cleaned ------")
        if not loop:
            return count

    @dm_cleanup.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

    @commands.command()
    @checks.is_owner()
    async def clean_dm(self, ctx):
        """Manually clean forgotten DMs.

        DMs that Meowth forgot about will be cleaned automatically once per
        week. This command does it on command."""
        async with ctx.typing():
            count = await self.dm_cleanup_func(loop=False)
            await ctx.send(f"{count} DMs cleaned.")

    @commands.command(name='embed')
    @checks.serverowner_or_permissions(manage_message=True)
    async def _embed(self, ctx, title, content=None, colour=None,
                     icon_url=None, image_url=None, thumbnail_url=None,
                     plain_msg=''):
        """Build and post an embed in the current channel.

        Note: Always use quotes to contain multiple words within one argument.
        """
        await ctx.embed(title=title, description=content, colour=colour,
                        icon=icon_url, image=image_url,
                        thumbnail=thumbnail_url, plain_msg=plain_msg)

    @commands.command(hidden=True)
    async def template(self, ctx, *, sample_message):
        """Sample template messages to see how they would appear."""
        embed = None
        (msg, errors) = do_template(sample_message, ctx.author, ctx.guild)
        if errors:
            if msg.startswith('[') and msg.endswith(']'):
                embed = discord.Embed(
                    colour=ctx.guild.me.colour, description=msg[1:(- 1)])
                embed.add_field(name=_('Warning'), value=_('The following could not be found:\n{}').format(
                    '\n'.join(errors)))
                await ctx.channel.send(embed=embed)
            else:
                msg = _('{}\n\n**Warning:**\nThe following could not be found: {}').format(
                    msg, ', '.join(errors))
                await ctx.channel.send(msg)
        elif msg.startswith('[') and msg.endswith(']'):
            await ctx.channel.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=msg[1:(- 1)].format(user=ctx.author.mention)))
        else:
            await ctx.channel.send(msg.format(user=ctx.author.mention))

    @commands.command(hidden=True)
    @commands.has_permissions(manage_guild=True)
    async def outputlog(self, ctx):
        """Get current Meowth log.

        Usage: !outputlog
        Output is a link to mystbin."""
        with open(os.path.join('logs', 'meowth.log'), 'r', encoding='latin-1', errors='replace') as logfile:
            logdata = logfile.read()
        try:
            async def post(content, url='https://mystb.in/'):
                async with ClientSession() as session:
                    async with session.post(f'{url}/documents', data=content.encode('utf-8')) as post:
                        return '<' + url + (await post.json(content_type=None))['key'] + '>'
            log_file = await post(logdata)
            await ctx.channel.send(log_file)
        except Exception as e:
            print(e)
            await ctx.channel.send(f"Mystbin Error\n{e}", delete_after=10)

    @commands.command(aliases=['say'])
    @commands.has_permissions(manage_guild=True)
    async def announce(self, ctx, *, announce=None):
        """Repeats your message in an embed from Meowth.

        Usage: !announce [announcement]
        Surround announcement in brackets ([]) to send as an embed.
        Mentions will not work in embeds.
        If the announcement isn't added at the same time as the command, Meowth will wait 3 minutes for a followup message containing the announcement."""
        message = ctx.message
        channel = message.channel
        guild = message.guild
        author = message.author

        if announce == None:
            announcewait = await channel.send(_("I'll wait for your announcement!"), delete_after=180)
            announcemsg = await self.bot.wait_for('message', timeout=180, check=(lambda reply: reply.author == message.author))
            if announcemsg != None:
                announce = announcemsg.content
                await safe_delete(announcemsg)
            else:
                confirmation = await channel.send(_("Meowth! You took too long to send me your announcement! Retry when you're ready."), delete_after=10)
        embeddraft = discord.Embed(colour=guild.me.colour)
        if ctx.invoked_with == "announce":
            title = _('Announcement')
            if self.bot.user.avatar_url:
                embeddraft.set_author(name=title, icon_url=self.bot.user.avatar_url)
            else:
                embeddraft.set_author(name=title)
        embed_search = re.search(r'\[(.+)\]', announce)
        if embed_search:
            embeddraft.description = embed_search.group(1)
            announce = announce.replace("[", "").replace("]", "").replace(embed_search.group(1), "").strip()
            draft = await channel.send(announce, embed=embeddraft)
        else:
            draft = await channel.send(announce)

        reaction_list = ['❔', self.bot.custom_emoji.get('answer_yes', '\u2705'), self.bot.custom_emoji.get('answer_no', '\u274e')]
        owner_msg_add = ''
        if checks.is_owner_check(ctx):
            owner_msg_add = '🌎 '
            owner_msg_add += _('to send it to all servers, ')
            reaction_list.insert(0, '🌎')

        def check(reaction, user):
            if user.id == author.id:
                if (str(reaction.emoji) in reaction_list) and (reaction.message.id == rusure.id):
                    return True
            return False
        msg = _("That's what you sent, does it look good? React with ")
        msg += "{}❔ "
        msg += _("to send to another channel, ")
        msg += "{emoji} ".format(emoji=self.bot.custom_emoji.get('answer_yes', '\u2705'))
        msg += _("to send it to this channel, or ")
        msg += "{emoji} ".format(emoji=self.bot.custom_emoji.get('answer_no', '\u274e'))
        msg += _("to cancel")
        rusure = await channel.send(msg.format(owner_msg_add))
        try:
            timeout = False
            res, reactuser = await ask(self.bot, rusure, author.id, react_list=reaction_list)
        except TypeError:
            timeout = True
        if not timeout:
            await safe_delete(rusure)
            if res.emoji == self.bot.custom_emoji.get('answer_no', '\u274e'):
                confirmation = await channel.send(_('Announcement Cancelled.'), delete_after=10)
                await safe_delete(draft)
            elif res.emoji == self.bot.custom_emoji.get('answer_yes', '\u2705'):
                confirmation = await channel.send(_('Announcement Sent.'), delete_after=10)
            elif res.emoji == '❔':
                channelwait = await channel.send(_('What channel would you like me to send it to?'))
                channelmsg = await self.bot.wait_for('message', timeout=60, check=(lambda reply: reply.author == message.author))
                if channelmsg.content.isdigit():
                    sendchannel = self.bot.get_channel(int(channelmsg.content))
                elif channelmsg.raw_channel_mentions:
                    sendchannel = self.bot.get_channel(channelmsg.raw_channel_mentions[0])
                else:
                    sendchannel = discord.utils.get(guild.text_channels, name=channelmsg.content)
                if (channelmsg != None) and (sendchannel != None):
                    if announce.startswith("[") and announce.endswith("]"):
                        embeddraft.description = announce[1:-1]
                        announcement = await sendchannel.send(embed=embeddraft)
                    else:
                        announcement = await sendchannel.send(announce)
                    confirmation = await channel.send(_('Announcement Sent.'), delete_after=10)
                elif sendchannel == None:
                    confirmation = await channel.send(_("Meowth! That channel doesn't exist! Retry when you're ready."), delete_after=10)
                else:
                    confirmation = await channel.send(_("Meowth! You took too long to send me your announcement! Retry when you're ready."), delete_after=10)
                await safe_delete(channelwait)
                await safe_delete(channelmsg)
                await safe_delete(draft)
            elif (res.emoji == '🌎') and checks.is_owner_check(ctx):
                failed = 0
                sent = 0
                count = 0
                recipients = {

                }
                embeddraft.set_footer(text=_('For support, contact us on our Discord server. Invite Code: hhVjAN8'))
                embeddraft.colour = discord.Colour.lighter_grey()
                for guild in self.bot.guilds:
                    recipients[guild.name] = guild.owner
                for (guild, destination) in recipients.items():
                    try:
                        await destination.send(embed=embeddraft)
                    except discord.HTTPException:
                        failed += 1
                        logger.info('Announcement Delivery Failure: {} - {}'.format(destination.name, guild))
                    else:
                        sent += 1
                    count += 1
                logger.info('Announcement sent to {} server owners: {} successful, {} failed.'.format(count, sent, failed))
                confirmation = await channel.send(_('Announcement sent to {} server owners: {} successful, {} failed.').format(count, sent, failed), delete_after=10)
        else:
            await safe_delete(rusure)
            confirmation = await channel.send(_('Announcement Timed Out.'), delete_after=10)
        await asyncio.sleep(30)
        await safe_delete(message)

    @commands.command(name="uptime", hidden=True)
    async def _uptime(self, ctx):
        """Shows bot's uptime"""
        uptime_str = ctx.bot.uptime_str
        embed = discord.Embed(colour=ctx.guild.me.colour, description=uptime_str)
        embed.set_author(name="Uptime", icon_url=self.bot.user.avatar_url)
        try:
            await ctx.send(embed=embed)
        except discord.errors.Forbidden:
            await ctx.send("Uptime: {}".format(uptime_str))

    @commands.command()
    @checks.guildchannel()
    async def about(self, ctx):
        'Shows info about Meowth'
        huntr_repo = 'https://github.com/doonce/Meowth'
        huntr_name = 'BrenenP'
        guild_url = 'https://discord.gg/Qwb8xev'
        owner = self.bot.get_user(self.bot.owner)
        channel = ctx.channel
        uptime_str = self.bot.uptime_str
        yourguild = ctx.guild.name
        yourmembers = len(ctx.guild.members)
        embed_colour = ctx.guild.me.colour or discord.Colour.lighter_grey()
        about = _("I'm Meowth! A Pokemon Go helper bot for Discord!\n\nHuntr integration was implemented by [{huntr_name}]({huntr_repo}).\n\n[Join our server]({server_invite}) if you have any questions or feedback.\n\n").format(huntr_name=huntr_name, huntr_repo=huntr_repo, server_invite=guild_url)
        member_count = 0
        guild_count = 0
        for guild in self.bot.guilds:
            guild_count += 1
            member_count += len(guild.members)
        embed = discord.Embed(colour=embed_colour, description=about)
        embed.set_author(name="About Meowth", icon_url=self.bot.user.avatar_url)
        embed.add_field(name='Owner', value=owner)
        if guild_count > 1:
            embed.add_field(name='Servers', value=guild_count)
            embed.add_field(name='Members', value=member_count)
        embed.add_field(name='Your Server', value=yourguild)
        embed.add_field(name='Your Members', value=yourmembers)
        embed.add_field(name='Uptime', value=uptime_str)
        embed.set_footer(text="Running Meowth v19.7.9.1 | Built with discord.py")
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            await channel.send(_('I need the `Embed links` permission to send this'))

    @commands.group(name='set', case_insensitive=True)
    async def _set(self, ctx):
        """Changes a setting.

        Manager: timezone, regional, prefix
        Owner: avatar, username, activity, status"""
        if ctx.invoked_subcommand == None:
            raise commands.BadArgument()
            return

    @_set.command()
    @commands.has_permissions(manage_guild=True)
    async def regional(self, ctx, regional):
        """Changes server regional pokemon."""
        if regional.isdigit():
            regional = int(regional)
        else:
            regional = regional.lower()
            if regional == "reset" and checks.is_manager_check(ctx):
                msg = _("Are you sure you want to clear all regionals?")
                question = await ctx.channel.send(msg)
                try:
                    timeout = False
                    res, reactuser = await ask(self.bot, question, ctx.message.author.id)
                except TypeError:
                    timeout = True
                await safe_delete(question)
                if timeout or res.emoji == self.bot.custom_emoji.get('answer_no', '\u274e'):
                    return
                elif res.emoji == self.bot.custom_emoji.get('answer_yes', '\u2705'):
                    pass
                else:
                    return
                guild_dict_copy = copy.deepcopy(self.bot.guild_dict)
                for guildid in guild_dict_copy.keys():
                    self.bot.guild_dict[guildid]['configure_dict']['settings']['regional'] = None
                return
            elif regional == 'clear':
                regional = None
                self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['regional'] = regional
                await ctx.message.channel.send(_("Meowth! Regional raid boss cleared!"), delete_after=10)
                return
            else:
                regional = get_number(self.bot, regional)
        if regional in self.bot.raid_list:
            self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['regional'] = regional
            await ctx.message.channel.send(_("Meowth! Regional raid boss set to **{boss}**!").format(boss=get_name(self.bot, regional).title()), delete_after=10)
            await safe_reaction(ctx.message, self.bot.custom_emoji.get('command_done', '\u2611'))
        else:
            await ctx.message.channel.send(_("Meowth! That Pokemon doesn't appear in raids!"), delete_after=10)
            return

    @_set.command()
    @checks.guildchannel()
    async def timezone(self, ctx, *, timezone: str = ''):
        """Changes server timezone."""
        if not ctx.author.guild_permissions.manage_guild:
            if not checks.is_manager_check(ctx):
                return
        try:
            timezone = float(timezone)
        except ValueError:
            await ctx.channel.send(_("I couldn't convert your answer to an appropriate timezone! Please double check what you sent me and resend a number from **-12** to **12**."), delete_after=10)
            return
        if (not ((- 12) <= timezone <= 14)):
            await ctx.channel.send(_("I couldn't convert your answer to an appropriate timezone! Please double check what you sent me and resend a number from **-12** to **12**."), delete_after=10)
            return
        self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['offset'] = timezone
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.channel.guild.id]['configure_dict']['settings']['offset'])
        await ctx.channel.send(_("Timezone has been set to: `UTC{offset}`\nThe current time is **{now}**").format(offset=timezone, now=now.strftime("%H:%M")), delete_after=10)
        await safe_reaction(ctx.message, self.bot.custom_emoji.get('command_done', '\u2611'))

    @_set.command()
    @checks.is_owner()
    async def status(self, ctx, *, status: str):
        """Sets the bot's online status
        Available statuses include: online, idle, dnd, invisible
        """

        statuses = {
            "online"    : discord.Status.online,
            "idle"      : discord.Status.idle,
            "dnd"       : discord.Status.dnd,
            "invisible" : discord.Status.invisible
            }

        game = ctx.me.activity

        try:
            status = statuses[status.lower()]
        except KeyError:
            await ctx.bot.send_cmd_help(ctx)
        else:
            await ctx.bot.change_presence(status=status,
                                          activity=game)

    @_set.command()
    @checks.is_owner()
    async def nickname(self, ctx, *, nickname: str):
        """Sets bot's nickname"""
        try:
            await ctx.guild.me.edit(nick=nickname)
        except discord.Forbidden:
            await ctx.send("Meowth! An error occured when trying to change my nickname, try again later.", delete_after=10)

    @_set.command()
    @checks.is_owner()
    async def avatar(self, ctx, *, avatar: str = None):
        """Changes Meowth's Avatar to attached image or URL."""
        avy_url = None
        old_avy = self.bot.user.avatar_url_as(static_format="png")
        if avatar and "http" in avatar:
            for word in avatar.split():
                if "http" in word and (".png" in word.lower() or ".jpg" in word.lower() or ".jpeg" in word.lower() or ".gif" in word.lower()):
                    avy_url = word
                    break
        elif ctx.message.attachments:
            avatar = ctx.message.attachments[0]
            if not avatar.height:
                avy_url = None
            else:
                avy_url = avatar.url
        else:
            avy_url = None
        if avy_url:
            rusure = await ctx.send("Would you like to change my avatar?")
            try:
                timeout = False
                res, reactuser = await ask(self.bot, rusure, ctx.author.id)
            except TypeError:
                timeout = True
            if timeout or res.emoji == self.bot.custom_emoji.get('answer_no', '\u274e'):
                await safe_delete(rusure)
                confirmation = await message.channel.send(_('Configuration Cancelled.'), delete_after=10)
            elif res.emoji == self.bot.custom_emoji.get('answer_yes', '\u2705'):
                await safe_delete(rusure)
                async with aiohttp.ClientSession() as cs:
                    async with cs.get(avy_url) as r:
                        try:
                            await self.bot.user.edit(avatar=await r.read())
                            await ctx.send(embed=discord.Embed(title="**Avatar Changed**", colour=ctx.guild.me.colour, description=f"Old Avatar: {old_avy}\nNew Avatar: {avy_url}"))
                        except (discord.errors.HTTPException, discord.errors.ClientException, discord.errors.InvalidArgument):
                            await ctx.send("Meowth! An error occured when trying to change my avatar. There is a low rate limit on doing this, try again later.", delete_after=10)
        else:
            await ctx.send("Meowth! I couldn't find an attachment or img URL. Please make sure your URL is an image file (png, jpg, jpeg, or gif).", delete_after=10)
        await asyncio.sleep(10)
        await safe_delete(ctx.message)

    @_set.command()
    @checks.is_owner()
    async def username(self, ctx, *, username):
        """Changes Meowth's Username."""
        old_username = self.bot.user.name
        rusure = await ctx.send(f"Would you like to change my username from **{old_username}** to **{username}**?")
        try:
            timeout = False
            res, reactuser = await ask(self.bot, rusure, ctx.author.id)
        except TypeError:
            timeout = True
        if timeout or res.emoji == self.bot.custom_emoji.get('answer_no', '\u274e'):
            await safe_delete(rusure)
            confirmation = await ctx.send(_('Configuration Cancelled.'), delete_after=10)
        elif res.emoji == self.bot.custom_emoji.get('answer_yes', '\u2705'):
            await safe_delete(rusure)
            try:
                await self.bot.user.edit(username=username)
            except (discord.errors.HTTPException, discord.errors.ClientException, discord.errors.InvalidArgument):
                await ctx.send("Meowth! An error occured when trying to change my username. There is a low rate limit on doing this, try again later.", delete_after=10)
        await asyncio.sleep(10)
        await safe_delete(ctx.message)

    @_set.command()
    @checks.is_owner()
    async def activity(self, ctx, *, activity):
        """Changes Meowth's Activity."""
        old_activity = ctx.guild.me.activities[0].name
        rusure = await ctx.send(f"Would you like to change my activity from **{old_activity}** to **{activity}**?")
        try:
            timeout = False
            res, reactuser = await ask(self.bot, rusure, ctx.author.id)
        except TypeError:
            timeout = True
        if timeout or res.emoji == self.bot.custom_emoji.get('answer_no', '\u274e'):
            await safe_delete(rusure)
            confirmation = await ctx.send(_('Configuration Cancelled.'), delete_after=10)
        elif res.emoji == self.bot.custom_emoji.get('answer_yes', '\u2705'):
            await safe_delete(rusure)
            try:
                await self.bot.change_presence(activity=discord.Game(name=activity))
            except discord.errors.InvalidArgument:
                await ctx.send("Meowth! An error occured when trying to change my activity.", delete_after=10)
        await asyncio.sleep(10)
        await safe_delete(ctx.message)

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def prefix(self, ctx, prefix=None):
        """Get and set server prefix."""
        if not prefix:
            prefix = self.bot._get_prefix(self.bot, ctx.message)
            return await ctx.channel.send(_('Prefix for this server is: `{}`').format(prefix), delete_after=10)
        if prefix == 'clear':
            prefix = None
        prefix = prefix.strip()
        self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['prefix'] = prefix
        if prefix != None:
            await ctx.channel.send(_('Prefix has been set to: `{}`').format(prefix))
        else:
            default_prefix = self.bot.default_prefix
            await ctx.channel.send(_('Prefix has been reset to default: `{}`').format(default_prefix))
        await safe_reaction(ctx.message, self.bot.custom_emoji.get('command_done', '\u2611'))

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def permissions(self, ctx, channel_id = None):
        """Show Meowth's permissions for the guild and channel."""
        channel = discord.utils.get(ctx.bot.get_all_channels(), id=channel_id)
        guild = channel.guild if channel else ctx.guild
        channel = channel or ctx.channel
        guild_perms = guild.me.guild_permissions
        chan_perms = channel.permissions_for(guild.me)
        req_perms = discord.Permissions(268822608)

        embed = discord.Embed(colour=ctx.guild.me.colour)
        embed.set_author(name=_('Bot Permissions'), icon_url="https://i.imgur.com/wzryVaS.png")

        wrap = functools.partial(textwrap.wrap, width=20)
        names = [wrap(channel.name), wrap(guild.name)]
        if channel.category:
            names.append(wrap(channel.category.name))
        name_len = max(len(n) for n in names)
        def same_len(txt):
            return '\n'.join(txt + ([' '] * (name_len-len(txt))))
        names = [same_len(n) for n in names]
        chan_msg = [f"**{names[0]}** \n{channel.id} \n"]
        guild_msg = [f"**{names[1]}** \n{guild.id} \n"]
        def perms_result(perms):
            data = []
            meet_req = perms >= req_perms
            result = _("**PASS**") if meet_req else _("**FAIL**")
            data.append(f"{result} - {perms.value} \n")
            true_perms = [k for k, v in dict(perms).items() if v is True]
            false_perms = [k for k, v in dict(perms).items() if v is False]
            req_perms_list = [k for k, v in dict(req_perms).items() if v is True]
            true_perms_str = '\n'.join(true_perms)
            if not meet_req:
                missing = '\n'.join([p for p in false_perms if p in req_perms_list])
                meet_req_result = _("**MISSING**")
                data.append(f"{meet_req_result} \n{missing} \n")
            if true_perms_str:
                meet_req_result = _("**ENABLED**")
                data.append(f"{meet_req_result} \n{true_perms_str} \n")
            return '\n'.join(data)
        guild_msg.append(perms_result(guild_perms))
        chan_msg.append(perms_result(chan_perms))
        embed.add_field(name=_('GUILD'), value='\n'.join(guild_msg))
        if channel.category:
            cat_perms = channel.category.permissions_for(guild.me)
            cat_msg = [f"**{names[2]}** \n{channel.category.id} \n"]
            cat_msg.append(perms_result(cat_perms))
            embed.add_field(name=_('CATEGORY'), value='\n'.join(cat_msg))
        embed.add_field(name=_('CHANNEL'), value='\n'.join(chan_msg))

        try:
            await ctx.send(embed=embed)
        except discord.errors.Forbidden:
            # didn't have permissions to send a message with an embed
            try:
                msg = _("I couldn't send an embed here, so I've sent you a DM")
                await ctx.send(msg)
            except discord.errors.Forbidden:
                # didn't have permissions to send a message at all
                pass
            await ctx.author.send(embed=embed)

def setup(bot):
    bot.add_cog(Utilities(bot))

def teardown(bot):
    bot.remove_cog(Utilities)
