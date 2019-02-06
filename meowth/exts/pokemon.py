from string import ascii_lowercase

import discord
import re
from discord.ext import commands
from discord.ext.commands import CommandError

from meowth import utils


class PokemonNotFound(CommandError):
    """Exception raised when Pokemon given does not exist."""
    def __init__(self, pokemon, retry=True):
        self.pokemon = pokemon
        self.retry = retry

class Pokemon():
    """Represents a Pokemon.

    This class contains the attributes of a specific pokemon, and
    provides methods of which to get specific info and results on it.

    Parameters
    -----------
    bot: :class:`eevee.core.bot.Eevee`
        Current instance of Eevee
    pkmn: str or int
        The name or id of a Pokemon
    guild: :class:`discord.Guild`, optional
        The guild that is requesting the Pokemon
    moveset: :class:`list` or :class:`tuple` of :class:`str`, optional
        `kwarg-only:` The two moves of this Pokemon
    weather: :class:`str`, optional
        `kwarg-only:` Weather during the encounter

    Raises
    -------
    :exc:`.errors.PokemonNotFound`
        The pkmn argument was not a valid index and was not found in the
        list of Pokemon names.

    Attributes
    -----------
    name: :class:`str`
        Lowercase string representing the name of the Pokemon
    id: :class:`int`
        Pokemon ID number
    types: :class:`list` of :class:`str`
        A :class:`list` of the Pokemon's types
    moveset: :class:`list` or :class:`tuple` of :class:`str`
        The two moves of this Pokemon
    weather: :class:`str`
        Weather during the encounter
    guild: :class:`discord.Guild`
        Guild that created the Pokemon
    bot: :class:`eevee.core.bot.Eevee`
        Current instance of Eevee
    """

    __slots__ = ('name', 'id', 'types', 'bot', 'guild', 'pkmn_list',
                 'pb_raid', 'weather', 'moveset', 'form', 'shiny', 'gender',
                 'alolan', 'size', 'legendary', 'mythical')

    def generate_lists(bot):
        shiny_dict = {}
        alolan_list = []
        gender_dict = {}
        legendary_list = []
        mythical_list = []
        form_dict = {}
        form_list = []
        two_words = []
        for k, v in bot.pkmn_info.items():
            shiny_forms = []
            gender_forms = []
            for form in v["forms"]:
                if form == "list":
                    continue
                if v["forms"][form].get("shiny", False):
                    shiny_forms.append(form)
                if v["forms"][form].get("gender", False):
                    gender_forms.append(form)
            if shiny_forms:
                shiny_dict[v["number"]] = shiny_forms
            if gender_forms:
                gender_dict[v["number"]] = gender_forms
            if v['forms'].get('alolan', {}):
                alolan_list.append(bot.pkmn_info[k]['number'])
            if v['legendary']:
                legendary_list.append(bot.pkmn_info[k]['number'])
            if v['mythical']:
                mythical_list.append(bot.pkmn_info[k]['number'])
            if v['forms'].get('list', []) and v['forms'].get('list', []) != ["none"]:
                number = v['number']
                form_dict[number] = v['forms']['list']
            if len(k.split()) > 1:
                for word in k.split():
                    two_words.append(word)
                    two_words.append(re.sub('[^a-zA-Z0-9]', '', word))
        for pkmn in form_dict:
            for f in form_dict[pkmn]:
                if f not in form_list:
                    form_list.append(f)
        form_list = list(set(form_list) - set(ascii_lowercase) - set(['1', '2', '3', '4', '5', '6', '7', '8', '?', '!']))
        form_list.extend(' ' + c for c in ascii_lowercase)
        form_list.extend(c for c in [' 1', ' 2', ' 3', ' 4', ' 5', ' 6', ' 7', ' 8', ' ?', ' !'])
        form_dict['list'] = form_list
        form_dict['two_words'] = two_words
        bot.alolan_list = alolan_list
        bot.gender_dict = gender_dict
        bot.legendary_list = legendary_list
        bot.mythical_list = mythical_list
        bot.form_dict = form_dict
        bot.shiny_dict = shiny_dict

    def __init__(self, bot, pkmn, guild=None, **attribs):
        self.bot = bot
        self.guild = guild
        self.pkmn_list = bot.pkmn_list

        if pkmn.isdigit():
            pkmn = utils.get_name(bot, pkmn)

        self.name = pkmn
        if pkmn not in self.pkmn_list:
            raise PokemonNotFound(pkmn)
        self.id = utils.get_number(bot, pkmn)
        self.types = self._get_type()
        self.pb_raid = None
        self.weather = attribs.get('weather', None)
        self.moveset = attribs.get('moveset', [])
        self.size = attribs.get('size', None)
        self.form = attribs.get('form', '')
        if self.form not in bot.form_dict.get(self.id, []):
            self.form = None
        self.alolan = attribs.get('alolan', False)
        if self.id not in bot.alolan_list:
            self.alolan = False
        self.shiny = attribs.get('shiny', False)
        if self.shiny:
            if self.id not in bot.shiny_dict:
                self.shiny = False
            if self.alolan and "alolan" not in bot.shiny_dict.get(self.id, []):
                self.shiny = False
            elif str(self.form).lower() not in bot.shiny_dict.get(self.id, []):
                self.shiny = False
        if self.id in bot.legendary_list:
            self.legendary = True
        elif self.id in bot.mythical_list:
            self.mythical = True
        else:
            self.legendary = False
            self.mythical = False
        self.gender = attribs.get('gender', None)
        if self.id not in bot.gender_dict:
            self.gender = None

    def __str__(self):
        name = self.name.title()
        if self.size:
            name = f"{self.size} {name}"
        if self.form:
            name = name + f" {self.form.title()}"
        if self.alolan:
            name = 'Alolan ' + name
        if self.shiny:
            name = 'Shiny ' + name
        if self.gender:
            name = str(self.gender).title() + ' ' + name
        return name

    async def get_pb_raid(self, weather=None, userid=None, moveset=None):
        """Get a PokeBattler Raid for this Pokemon

        This can quickly produce a PokeBattler Raid for the current
        Pokemon, with the option of providing a PokeBattler User ID to
        get customised results.

        The resulting PokeBattler Raid object will be saved under the
        `pb_raid` attribute of the Pokemon instance for later retrieval,
        unless it's customised with an ID.

        Parameters
        -----------
        weather: :class:`str`, optional
            The weather during the raid
        userid: :class:`int`, optional
            The Pokebattler User ID to generate the PB Raid with
        moveset: list or tuple, optional
            A :class:`list` or :class:`tuple` with a :class:`str` representing
            ``move1`` and ``move2`` of the Pokemon.

        Returns
        --------
        :class:`eevee.cogs.pokebattler.objects.PBRaid` or :obj:`None`
            PokeBattler Raid instance or None if not a Raid Pokemon.

        Example
        --------

        .. code-block:: python3

            pokemon = Pokemon(ctx.bot, 'Groudon')
            moveset = ('Dragon Tail', 'Solar Beam')
            pb_raid = pokemon.get_pb_raid('windy', 12345, moveset)
        """

        # if a Pokebattler Raid exists with the same settings, return it
        if self.pb_raid:
            if not (weather or userid) and not moveset:
                return self.pb_raid
            if weather:
                self.pb_raid.change_weather(weather)

        # if it doesn't exist or settings changed, generate it
        else:
            pb_cog = self.bot.cogs.get('PokeBattler', None)
            if not pb_cog:
                return None
            if not weather:
                weather = self.weather or 'DEFAULT'
            weather = pb_cog.PBRaid.get_weather(weather)
            pb_raid = await pb_cog.PBRaid.get(
                self.bot, self, weather=self.weather, userid=userid)

        # set the moveset for the Pokebattler Raid
        if not moveset:
            moveset = self.moveset
        try:
            pb_raid.set_moveset(moveset)
        except RuntimeError:
            pass

        # don't save it if it's a user-specific Pokebattler Raid
        if not userid:
            self.pb_raid = pb_raid

        return pb_raid

    @property
    def pokedex(self):
        """:class:`str` : Pokemon Pokedex Entry"""
        pkmn_name = str(self.name).lower()
        pkmn_form = str(self.form).lower()
        if self.alolan:
            pkmn_form = "alolan"
        if not pkmn_form:
            pkmn_form = "none"
        return self.bot.pkmn_info[pkmn_name]['forms'][pkmn_form]['pokedex']

    @property
    def img_url(self):
        """:class:`str` : Pokemon sprite image URL"""
        pkmn_no = str(self.id).zfill(3)
        form_str = ""
        if self.id in self.bot.gender_dict:
            if self.gender == 'female':
                form_str = "_01"
            else:
                form_str = "_00"
        if self.form and self.id in self.bot.form_dict:
            if self.id in [201, 327, 351, 386, 413, 421, 423, 423, 487, 492]:
                form_str = form_str + "_" + str(self.bot.form_dict[self.id].index(self.form) + 11)
            elif self.form == "sunglasses":
                form_str = form_str + "_00_05"
            else:
                form_str = form_str + "_" + str(self.bot.form_dict[self.id].index(self.form) + 1).zfill(2)
        if self.id not in self.bot.gender_dict and not self.form:
            form_str = form_str + "_00"
        if self.alolan:
            form_str = "_61"
        if self.shiny:
            shiny_str = "_shiny"
        else:
            shiny_str = ""

        return (f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/pkmn_icons/pokemon_icon_{pkmn_no}{form_str}{shiny_str}.png?cache=2")

    # async def colour(self):
    #     """:class:`discord.Colour` : Discord colour based on Pokemon sprite."""
    #     return await url_color(self.img_url)

    @property
    def is_raid(self):
        """:class:`bool` : Indicates if the pokemon can show in Raids"""
        return self.id in utils.get_raidlist(self.bot)

    @property
    def is_exraid(self):
        """:class:`bool` : Indicates if the pokemon can show in Raids"""
        if not self.is_raid:
            return False
        return self.id in self.bot.raid_info['raid_eggs']['EX']['pokemon']

    @property
    def raid_level(self):
        """:class:`int` or :obj:`None` : Returns raid egg level"""
        return utils.get_level(self.bot, self.id)

    # def max_raid_cp(self, weather_boost=False):
    #     """:class:`int` or :obj:`None` : Returns max CP on capture after raid
    #     """
    #     key = "max_cp_w" if weather_boost else "max_cp"
    #     return self.bot.raid_pokemon[self.name][key] if self.is_raid else None

    def role(self, guild=None):
        """:class:`discord.Role` or :obj:`None` : Returns the role for
        this Pokemon
        """
        if not guild:
            guild = self.guild
        if not guild:
            return None
        return discord.utils.get(guild.roles, name=self.name)

    def set_guild(self, guild):
        """:class:`discord.Guild` or :obj:`None` : Sets the relevant Guild"""
        self.guild = guild

    @property
    def weak_against(self):
        """:class:`dict` : Returns a dict of all types the Pokemon is
        weak against.
        """
        types_eff = {}
        for t, v in self.type_effects.items():
            if round(v, 3) > 1:
                types_eff[t] = v
        return types_eff

    @property
    def strong_against(self):
        """:class:`dict` : Returns a dict of all types the Pokemon is
        strong against.
        """
        types_eff = {}
        for t, v in self.type_effects.items():
            if round(v, 3) < 1:
                types_eff[t] = v
        return types_eff

    def _get_type(self):
        """:class:`list` : Returns the Pokemon's types"""
        return self.bot.pkmn_info[utils.get_name(self.bot, self.id)]['forms']['none']['type']

    @property
    def type_effects(self):
        """:class:`dict` : Returns a dict of all Pokemon types and their
        relative effectiveness as values.
        """
        type_eff = {}
        for _type in self.types:
            for atk_type in self.bot.type_chart[_type]:
                if atk_type not in type_eff:
                    type_eff[atk_type] = 1
                type_eff[atk_type] *= self.bot.type_chart[_type][atk_type]
        return type_eff

    @property
    def type_effects_grouped(self):
        """:class:`dict` : Returns a dict of all Pokemon types and their
        relative effectiveness as values, grouped by the following:
            * ultra
            * super
            * low
            * worst
        """
        type_eff_dict = {
            'ultra' : [],
            'super' : [],
            'low'   : [],
            'worst' : []
        }
        for t, v in self.type_effects.items():
            if v > 1.9:
                type_eff_dict['ultra'].append(t)
            elif v > 1.3:
                type_eff_dict['super'].append(t)
            elif v < 0.6:
                type_eff_dict['worst'].append(t)
            else:
                type_eff_dict['low'].append(t)
        return type_eff_dict

    @classmethod
    async def convert(cls, ctx, argument):
        """Returns a pokemon that matches the value
        of the argument that's being converted.

        It first will check if it's a valid ID, and if not, will perform
        a fuzzymatch against the list of Pokemon names.

        Returns
        --------
        :class:`Pokemon` or :class:`dict`
            If there was a close or exact match, it will return a valid
            :class:`Pokemon`.
            If the match is lower than 80% likeness, it will return a
            :class:`dict` with the following keys:
                * ``suggested`` - Next best guess based on likeness.
                * ``original`` - Original value of argument provided.

        Raises
        -------
        :exc:`discord.ext.commands.BadArgument`
            The argument didn't match a Pokemon ID or name.
        """
        argument = str(argument)
        shiny = re.search(r'shiny', argument, re.IGNORECASE)
        alolan = re.search(r'alolan', argument, re.IGNORECASE)
        male = re.search(r'(?<!fe)male', argument, re.IGNORECASE)
        female = re.search(r'female', argument, re.IGNORECASE)
        large = re.search(r'large|big|xl', argument, re.IGNORECASE)
        small = re.search(r'small|tiny|xs', argument, re.IGNORECASE)
        form_list = ctx.bot.form_dict['list']
        try:
            form_list.remove("none")
        except ValueError:
            pass
        one_char_forms = re.search(r'{unown}|201|{spinda}|327'.format(unown=ctx.bot.pkmn_list[200], spinda=ctx.bot.pkmn_list[326]), argument, re.IGNORECASE)
        if not one_char_forms:
            form_list = list(set(form_list) - set([' ' + c for c in ascii_lowercase]) - set([' 1', ' 2', ' 3', ' 4', ' 5', ' 6', ' 7', ' 8', ' ?', ' !']))
        ash_forms = re.search(r'{pichu}|172|{pikachu}|25|{raichu}|26|{greninja}|658'.format(pichu=ctx.bot.pkmn_list[171], pikachu=ctx.bot.pkmn_list[24], raichu=ctx.bot.pkmn_list[25], greninja=ctx.bot.pkmn_list[657]), argument, re.IGNORECASE)
        if not ash_forms:
            form_list = list(set(form_list) - set(['ash']))

        if shiny:
            argument = argument.replace(shiny.group(0), '').strip()
            shiny = True
        else:
            shiny = False
        if alolan:
            argument = argument.replace(alolan.group(0), '').strip()
            alolan = True
        else:
            alolan = False
        if male:
            argument = argument.replace(male.group(0), '').strip()
            gender = "male"
        elif female:
            argument = argument.replace(female.group(0), '').strip()
            gender = "female"
        else:
            gender = None
        if large:
            size = "XL"
            argument = argument.replace(large.group(0), '').strip()
        elif small:
            size = "XS"
            argument = argument.replace(small.group(0), '').strip()
        else:
            size = None

        for form in form_list:
            form = re.search(form, argument, re.IGNORECASE)
            if form:
                argument = argument.replace(form.group(0), '').strip()
                form = form.group(0).lower().strip()
                break
            else:
                form = None

        for word in argument.split():
            if word.lower() not in ctx.bot.pkmn_list and not word.isdigit() and word.lower() not in ctx.bot.form_dict['two_words']:
                match, score = utils.get_match(ctx.bot.pkmn_list, word)
                if not score or score < 80:
                    argument = argument.replace(word, '').strip()
                else:
                    argument = argument.replace(word, match).strip()

        if argument.isdigit():
            try:
                match = utils.get_name(ctx.bot, int(argument))
                score = 100
            except IndexError:
                raise commands.errors.BadArgument(
                    'Pokemon ID "{}" not valid'.format(argument))
        elif argument in ctx.bot.pkmn_list:
            match = argument.lower()
            score = 100
        else:
            match, score = utils.get_match(ctx.bot.pkmn_list, argument)

        result = False
        if match:
            if score >= 80:
                result = cls(ctx.bot, str(match), ctx.guild, shiny=shiny, alolan=alolan, form=form, gender=gender, size=size)
            else:
                result = {
                    'suggested' : str(match),
                    'original'   : argument
                }
        if not result:
            raise commands.errors.BadArgument(
                'Pokemon "{}" not valid'.format(argument))

        return result

    @classmethod
    def get_pokemon(cls, bot, argument, allow_digits = True):
        argument = str(argument)
        shiny = re.search(r'shiny', argument, re.IGNORECASE)
        alolan = re.search(r'alolan', argument, re.IGNORECASE)
        male = re.search(r'(?<!fe)male', argument, re.IGNORECASE)
        female = re.search(r'female', argument, re.IGNORECASE)
        large = re.search(r'large|big|xl', argument, re.IGNORECASE)
        small = re.search(r'small|tiny|xs', argument, re.IGNORECASE)
        form_list = bot.form_dict['list']
        try:
            form_list.remove("none")
        except ValueError:
            pass
        one_char_forms = re.search(r'{unown}|201|{spinda}|327'.format(unown=bot.pkmn_list[200], spinda=bot.pkmn_list[326]), argument, re.IGNORECASE)
        if not one_char_forms:
            form_list = list(set(form_list) - set([' ' + c for c in ascii_lowercase]) - set([' 1', ' 2', ' 3', ' 4', ' 5', ' 6', ' 7', ' 8', ' ?', ' !']))
        ash_forms = re.search(r'{pichu}|172|{pikachu}|25|{raichu}|26|{greninja}|658'.format(pichu=bot.pkmn_list[171], pikachu=bot.pkmn_list[24], raichu=bot.pkmn_list[25], greninja=bot.pkmn_list[657]), argument, re.IGNORECASE)
        if not ash_forms:
            form_list = list(set(form_list) - set(['ash']))

        if shiny:
            argument = argument.replace(shiny.group(0), '').strip()
            shiny = True
        else:
            shiny = False
        if alolan:
            argument = argument.replace(alolan.group(0), '').strip()
            alolan = True
        else:
            alolan = False
        if male:
            argument = argument.replace(male.group(0), '').strip()
            gender = "male"
        elif female:
            argument = argument.replace(female.group(0), '').strip()
            gender = "female"
        else:
            gender = None
        if large:
            size = "XL"
            argument = argument.replace(large.group(0), '').strip()
        elif small:
            size = "XS"
            argument = argument.replace(small.group(0), '').strip()
        else:
            size = None

        for form in form_list:
            form = re.search(form, argument, re.IGNORECASE)
            if form:
                argument = argument.replace(form.group(0), '').strip()
                form = form.group(0).lower().strip()
                break
            else:
                form = None

        for word in argument.split():
            if word.lower() not in bot.pkmn_list and not word.isdigit() and word.lower() not in bot.form_dict['two_words']:
                match, score = utils.get_match(bot.pkmn_list, word)
                if not score or score < 80:
                    argument = argument.replace(word, '').strip()
                else:
                    argument = argument.replace(word, match).strip()

        if argument.isdigit() and allow_digits:
            match = utils.get_name(bot, int(argument))
        else:
            match = utils.get_match(bot.pkmn_list, argument)[0]

        if not match:
            return None

        pokemon = cls(bot, str(match), None, shiny=shiny, alolan=alolan, form=form, gender=gender, size=size)

        return pokemon

    @classmethod
    async def ask_pokemon(cls, ctx, argument, allow_digits = True):
        argument = str(argument)
        shiny = re.search(r'shiny', argument, re.IGNORECASE)
        alolan = re.search(r'alolan', argument, re.IGNORECASE)
        male = re.search(r'(?<!fe)male', argument, re.IGNORECASE)
        female = re.search(r'female', argument, re.IGNORECASE)
        large = re.search(r'large|big|xl', argument, re.IGNORECASE)
        small = re.search(r'small|tiny|xs', argument, re.IGNORECASE)
        form_list = ctx.bot.form_dict['list']
        pokemon = False
        try:
            form_list.remove("none")
        except ValueError:
            pass
        one_char_forms = re.search(r'{unown}|201|{spinda}|327'.format(unown=ctx.bot.pkmn_list[200], spinda=ctx.bot.pkmn_list[326]), argument, re.IGNORECASE)
        if not one_char_forms:
            form_list = list(set(form_list) - set([' ' + c for c in ascii_lowercase]) - set([' 1', ' 2', ' 3', ' 4', ' 5', ' 6', ' 7', ' 8', ' ?', ' !']))
        ash_forms = re.search(r'{pichu}|172|{pikachu}|25|{raichu}|26|{greninja}|658'.format(pichu=ctx.bot.pkmn_list[171], pikachu=ctx.bot.pkmn_list[24], raichu=ctx.bot.pkmn_list[25], greninja=ctx.bot.pkmn_list[657]), argument, re.IGNORECASE)
        if not ash_forms:
            form_list = list(set(form_list) - set(['ash']))
        pokemon = False
        match_list = []

        if shiny:
            match_list.append(shiny.group(0))
            argument = argument.replace(shiny.group(0), '').strip()
            shiny = True
        else:
            shiny = False
        if alolan:
            match_list.append(alolan.group(0))
            argument = argument.replace(alolan.group(0), '').strip()
            alolan = True
        else:
            alolan = False
        if male:
            match_list.append(male.group(0))
            argument = argument.replace(male.group(0), '').strip()
            gender = "male"
        elif female:
            match_list.append(female.group(0))
            argument = argument.replace(female.group(0), '').strip()
            gender = "female"
        else:
            gender = None
        if large:
            size = "XL"
            match_list.append(large.group(0))
            argument = argument.replace(large.group(0), '').strip()
        elif small:
            size = "XS"
            match_list.append(small.group(0))
            argument = argument.replace(small.group(0), '').strip()
        else:
            size = None

        for form in form_list:
            form = re.search(form, argument, re.IGNORECASE)
            if form:
                match_list.append(form.group(0))
                argument = argument.replace(form.group(0), '').strip()
                form = form.group(0).lower().strip()
                break
            else:
                form = None

        for word in argument.split():
            if word.lower() in ctx.bot.pkmn_list:
                if pokemon:
                    argument = argument.replace(word, '').strip()
                else:
                    pokemon = word
                    match_list.append(word)
                    continue
            if word.lower() not in ctx.bot.pkmn_list and not word.isdigit() and word.lower() not in ctx.bot.form_dict['two_words']:
                if pokemon:
                    argument = argument.replace(word, '').strip()
                else:
                    match, score = utils.get_match(ctx.bot.pkmn_list, word)
                    if not score or score < 60:
                        argument = argument.replace(word, '').strip()
                    else:
                        match = await utils.autocorrect(ctx.bot, word, ctx.channel, ctx.author)
                        if not match:
                            return None, None
                        match_list.append(word)
                        argument = argument.replace(word, match).strip()
                        pokemon = match

        if not argument:
            return None, None

        if argument.isdigit() and allow_digits:
            match = utils.get_name(ctx.bot, int(argument))
        else:
            match = utils.get_match(ctx.bot.pkmn_list, argument.split()[0])[0]

        if not match:
            return None, None

        pokemon = cls(ctx.bot, str(match), None, shiny=shiny, alolan=alolan, form=form, gender=gender, size=size)

        return pokemon, match_list

class Pokedex:
    def __init__(self, bot):
        self.bot = bot

    @commands.command(hidden=True)
    async def sprite(self, ctx, *, sprite: Pokemon):
        preview_embed = discord.Embed(colour=utils.colour(ctx.guild))
        preview_embed.set_image(url=sprite.img_url)
        sprite_msg = await ctx.send(embed=preview_embed)

    @commands.command(hidden=True, aliases=['dex'])
    async def pokedex(self, ctx, *, pokemon: Pokemon):
        preview_embed = discord.Embed(colour=utils.colour(ctx.guild))
        pokemon.gender = False
        pokemon.size = None
        key_needed = False
        forms = [x.title() for x in ctx.bot.pkmn_info[pokemon.name.lower()]['forms']['list']]
        if not forms:
            forms = ["None"]
        form_list = []
        for form in forms:
            form_str = ""
            form_key = ""
            if form.lower() in ctx.bot.shiny_dict.get(pokemon.id, []):
                key_needed = True
                form_key += "S"
            if form.lower() in ctx.bot.gender_dict.get(pokemon.id, []):
                key_needed = True
                form_key += "G"
            if "S" in form_key or "G" in form_key:
                form_key = f"**({form_key})**"
            if form == "None":
                form = "Normal"
            form_str = f"{form} {form_key}"
            form_list.append(form_str.strip())
        preview_embed.add_field(name=f"{str(pokemon)} - #{pokemon.id} - {''.join(utils.get_type(self.bot, ctx.guild, pokemon.id, pokemon.form, pokemon.alolan))}", value=pokemon.pokedex, inline=False)
        if len(forms) > 1 or key_needed:
            preview_embed.add_field(name=f"{pokemon.name.title()} Forms:", value=", ".join(form_list), inline=True)
        if len(ctx.bot.pkmn_info[pokemon.name.lower()]["evolution"].split("→")) > 1:
            preview_embed.add_field(name=f"{pokemon.name.title()} Evolution:", value=ctx.bot.pkmn_info[pokemon.name.lower()]["evolution"], inline=False)
        if pokemon.id in ctx.bot.legendary_list:
            preview_embed.add_field(name="Legendary:", value=pokemon.id in ctx.bot.legendary_list, inline=True)
        if pokemon.id in ctx.bot.mythical_list:
            preview_embed.add_field(name="Mythical:", value=pokemon.id in ctx.bot.mythical_list, inline=True)
        preview_embed.set_thumbnail(url=pokemon.img_url)
        if key_needed:
            preview_embed.set_footer(text="S = Shiny Available | G = Gender Sprites")
        pokedex_msg = await ctx.send(embed=preview_embed)

def setup(bot):
    bot.add_cog(Pokedex(bot))
