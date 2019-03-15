import re

from fuzzywuzzy import fuzz
from fuzzywuzzy import process

import discord
import asyncio

from meowth.exts import pokemon as pkmn_class

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

def get_raidlist(bot):
    raidlist = []
    for level in bot.raid_info['raid_eggs']:
        for pkmn in bot.raid_info['raid_eggs'][level]['pokemon']:
            pokemon = pkmn_class.Pokemon.get_pokemon(bot, pkmn)
            raidlist.append(pokemon)
            raidlist.append(str(pokemon))
            raidlist.append(pokemon.name)
            raidlist.append(pokemon.id)
    return raidlist

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
        react_list=[bot.config['answer_yes'], bot.config['answer_no']]
    if user_list and type(user_list) != list:
        user_list = [user_list]
    def check(reaction, user):
        if user_list and type(user_list) is list:
            return (user.id in user_list) and (reaction.message.id == message.id) and (reaction.emoji in react_list)
        elif not user_list:
            return (user.id != message.author.id) and (reaction.message.id == message.id) and (reaction.emoji in react_list)
    for r in react_list:
        await asyncio.sleep(0.25)
        await message.add_reaction(r)
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
                member = guild.get_member(match)
            if (not member):
                not_found.append(full_match)
            return member.mention if member else full_match
        elif match_type == '#':
            channel = discord.utils.get(guild.text_channels, name=match)
            if match.isdigit() and (not channel):
                channel = guild.get_channel(match)
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
            if timeout or res.emoji == bot.config['answer_no']:
                return None
            elif res.emoji == bot.config['answer_yes']:
                return match
            else:
                return None
        else:
            return None
    else:
        question = await destination.send(msg)
        return None

def type_emoji(bot, guild, pokemon):
    if not pokemon.form:
        form = "none"
    if pokemon.alolan:
        form = "alolan"
    types = bot.pkmn_info[pokemon.name.lower()]['forms'][form]['type']
    ret = []
    for type in types:
        ret.append(parse_emoji(guild, bot.config['type_id_dict'][type.lower()]))
    return ret

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
                bot.config['type_id_dict'][weakness]) + x2) + ' '
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
            dm_message = await dm_channel.get_message(dm_message)
            await dm_message.delete()
        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
            pass

async def safe_delete(message):
    try:
        await message.delete()
    except (discord.errors.Forbidden, discord.errors.HTTPException, discord.errors.NotFound, AttributeError):
        pass

async def safe_get_message(channel, message_id):
    try:
        message = await channel.get_message(message_id)
    except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException, AttributeError):
        message = None
    return message
