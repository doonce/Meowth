
import asyncio
import copy
import re
import time
import datetime
import dateparser
import textwrap
import logging
import os
import json
import functools
import aiohttp
from dateutil.relativedelta import relativedelta
from string import ascii_lowercase
from math import log, floor

import discord
from discord.ext import commands, tasks
from discord.ext.commands import CommandError

from meowth import checks, errors
from meowth.exts import pokemon as pkmn_class
from meowth.exts import utilities as utils


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

    __slots__ = ('name', 'id', 'types', 'emoji', 'bot', 'guild', 'pkmn_list',
                 'pb_raid', 'weather', 'moveset', 'form', 'shiny', 'gender',
                 'alolan', 'size', 'legendary', 'mythical', 'base_stamina',
                 'base_attack', 'base_defense', 'charge_moves', 'quick_moves',
                 'height', 'weight', 'evolves', 'evolve_candy', 'buddy_distance',
                 'research_cp', 'raid_cp', 'boost_raid_cp', 'max_cp', 'weather')

    async def generate_lists(bot):
        available_dict = {}
        shiny_dict = {}
        alolan_list = []
        gender_dict = {}
        size_dict = {}
        legendary_list = []
        mythical_list = []
        form_dict = {}
        form_list = []
        two_words = []
        for k, v in bot.pkmn_info.items():
            gender_forms = []
            size_forms = []
            for form in v['forms']:
                if form == "list":
                    continue
                if v['forms'][form].get('shiny', []):
                    if v['number'] not in shiny_dict:
                        shiny_dict[v['number']] = {}
                    shiny_dict[v['number']][form] = v['forms'][form].get('shiny', [])
                if v['forms'][form].get('gender', False):
                    gender_forms.append(form)
                if v['forms'][form].get('size', False):
                    size_forms.append(form)
                if v['forms'][form].get('available', []):
                    if len(v['forms']) > 1:
                        if form not in form_list:
                            form_list.append(form)
                        if v['number'] not in available_dict:
                            available_dict[v['number']] = {}
                        available_dict[v['number']][form] = v['forms'][form].get('available', [])
            if gender_forms:
                gender_dict[v['number']] = gender_forms
            if size_forms:
                size_dict[v['number']] = size_forms
            if v['forms'].get('alolan', {}):
                alolan_list.append(bot.pkmn_info[k]['number'])
            if v['legendary']:
                legendary_list.append(bot.pkmn_info[k]['number'])
            if v['mythical']:
                mythical_list.append(bot.pkmn_info[k]['number'])
            if len(k.split()) > 1:
                for word in k.split():
                    two_words.append(word)
                    two_words.append(re.sub('[^a-zA-Z0-9]', '', word))
        form_dict = available_dict
        form_dict['list'] = form_list
        form_dict['two_words'] = two_words
        bot.size_dict = size_dict
        bot.alolan_list = alolan_list
        bot.gender_dict = gender_dict
        bot.legendary_list = legendary_list
        bot.mythical_list = mythical_list
        bot.form_dict = form_dict
        bot.shiny_dict = shiny_dict
        bot.gamemaster = {}
        async with aiohttp.ClientSession() as sess:
            async with sess.get("http://raw.githubusercontent.com/ZeChrales/PogoAssets/master/gamemaster/gamemaster.json") as resp:
                data = await resp.json(content_type=None)
                bot.gamemaster = data

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
        self.pb_raid = None
        self.weather = attribs.get('weather', None)
        self.moveset = attribs.get('moveset', [])
        self.size = attribs.get('size', None)
        self.form = attribs.get('form', '')
        if self.form not in bot.form_dict.get(self.id, {}):
            self.form = None
        self.alolan = attribs.get('alolan', False)
        if self.id not in bot.alolan_list:
            self.alolan = False
        self.shiny = attribs.get('shiny', False)
        if self.shiny:
            if self.id not in bot.shiny_dict:
                self.shiny = False
            if self.alolan and "alolan" not in bot.shiny_dict.get(self.id, {}):
                self.shiny = False
            elif self.form and str(self.form).lower() not in bot.shiny_dict.get(self.id, {}):
                self.shiny = False
        self.legendary = False
        self.mythical = False
        if self.id in bot.legendary_list:
            self.legendary = True
        if self.id in bot.mythical_list:
            self.mythical = True
        self.gender = attribs.get('gender', None)
        self.types = self._get_type()
        self.emoji = self._get_emoji()
        self.weather = None
        self.base_stamina = self.game_template.get('pokemonSettings', {}).get('stats', {}).get('baseStamina', None)
        self.base_attack = self.game_template.get('pokemonSettings', {}).get('stats', {}).get('baseAttack', None)
        self.base_defense = self.game_template.get('pokemonSettings', {}).get('stats', {}).get('baseDefense', None)
        if self.form == "armored":
            self.base_stamina = 214
            self.base_attack = 182
            self.base_defense = 278
        self.charge_moves = self.game_template.get('pokemonSettings', {}).get('cinematicMoves', None)
        self.quick_moves = self.game_template.get('pokemonSettings', {}).get('quickMoves', None)
        self.height = self.game_template.get('pokemonSettings', {}).get('pokedexHeightM', None)
        self.weight = self.game_template.get('pokemonSettings', {}).get('pokedexWeightKg', None)
        self.evolves = self.game_template.get('pokemonSettings', {}).get('evolutionIds', None)
        self.evolve_candy = self.game_template.get('pokemonSettings', {}).get('candyToEvolve', None)
        self.buddy_distance = self.game_template.get('pokemonSettings', {}).get('kmBuddyDistance', None)
        self.research_cp = f"{self._get_cp(15, 10, 10, 10)}-{self._get_cp(15, 15, 15, 15)}"
        self.raid_cp = f"{self._get_cp(20, 10, 10, 10)}-{self._get_cp(20, 15, 15, 15)}"
        self.boost_raid_cp = f"{self._get_cp(25, 10, 10, 10)}-{self._get_cp(25, 15, 15, 15)}"
        self.max_cp = f"{self._get_cp(40, 10, 10, 10)}-{self._get_cp(40, 15, 15, 15)}"

    def __str__(self):
        name = self.name.title()
        if self.id in self.bot.size_dict and self.size:
            if (self.alolan and "alolan" in self.bot.size_dict[self.id]) or str(self.form).lower() in self.bot.size_dict[self.id]:
                name = f"{self.size} {name}"
        if self.form:
            name = name + f" {self.form.title()}"
        if self.alolan:
            name = 'Alolan ' + name
        if self.shiny:
            name = 'Shiny ' + name
        if self.id in self.bot.gender_dict and self.gender:
            if (self.alolan and "alolan" in self.bot.gender_dict[self.id]) or (not self.alolan and str(self.form).lower() in self.bot.gender_dict[self.id]):
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
            if self.id in [201, 327, 351, 386, 412, 413, 421, 422, 423, 479, 487, 492, 493]:
                form_str = form_str + "_" + str(list(self.bot.form_dict[self.id].keys()).index(self.form) + 10)
            elif self.form == "sunglasses":
                form_str = form_str + "_00_05"
            elif self.id in [133, 134, 135, 136, 196, 197, 470, 471] and self.form == "flower":
                form_str = form_str + "_00_07"
            else:
                form_str = form_str + "_" + str(list(self.bot.form_dict[self.id].keys()).index(self.form)).zfill(2)
        if self.id not in self.bot.gender_dict and not self.form:
            form_str = form_str + "_00"
        if self.alolan:
            form_str = "_61"
        if self.shiny:
            shiny_str = "_shiny"
        else:
            shiny_str = ""

        return (f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/pkmn_icons/pokemon_icon_{pkmn_no}{form_str}{shiny_str}.png?cache=2")

    @property
    def game_name(self):
        template = {}
        search_term = f"{self.name}".lower()
        excluded_forms = list(self.bot.pkmn_info['pikachu']['forms'].keys()) + ["sunglasses"]
        if self.id == 201:
            excluded_forms.extend(list(self.bot.pkmn_info['unown']['forms'].keys()))
        elif self.id == 327:
            excluded_forms.extend(list(self.bot.pkmn_info['spinda']['forms'].keys()))
        form = copy.copy(self.form)
        if form == "armored":
            form = "a"
        if self.alolan:
            form = "alola"
        if form and form not in excluded_forms:
            search_term = f"{self.name}_{str(form).strip()}".lower()
        return search_term

    @property
    def game_template(self):
        template = {}
        search_term = f"V{str(self.id).zfill(4)}_pokemon_{self.game_name}".lower()
        if self.form == "armored":
            search_term = search_term.replace("_a", "")
        for template in self.bot.gamemaster.get('itemTemplates', {}):
            if search_term in template['templateId'].lower() and "forms_" not in template['templateId'].lower() and "spawn_" not in template['templateId'].lower() and "pokemon" in template['templateId'].lower():
                break
        return template

    # async def colour(self):
    #     """:class:`discord.Colour` : Discord colour based on Pokemon sprite."""
    #     return await url_color(self.img_url)

    @property
    def is_raid(self):
        """:class:`bool` : Indicates if the pokemon can show in Raids"""
        return str(self) in self.bot.raid_list or str(self).lower() in self.bot.raid_list

    @property
    def is_exraid(self):
        """:class:`bool` : Indicates if the pokemon can show in Raids"""
        if not self.is_raid:
            return False
        return str(self) in self.bot.raid_info['raid_eggs']['EX']['pokemon']

    @property
    def raid_level(self):
        """:class:`int` or :obj:`None` : Returns raid egg level"""
        return utils.get_level(self.bot, self.id)

    @property
    def is_boosted(self):
        clear_boost = ["Grass", "Ground", "Fire"]
        fog_boost = ["Dark", "Ghost"]
        cloudy_boost = ["Fairy", "Fighting", "Poison"]
        partlycloudy_boost = ["Normal", "Rock"]
        rainy_boost = ["Water", "Electric", "Bug"]
        snow_boost = ["Ice", "Steel"]
        windy_boost = ["Dragon", "Flying", "Psychic"]
        pkmn_types = self.types.copy()
        pkmn_types.append(None)
        for type in pkmn_types:
            if self.weather == "clear" and type in clear_boost:
                return "{emoji} ***Boosted***".format(emoji=self.bot.custom_emoji.get('clear', '\u2600'))
            elif self.weather == "foggy" and type in fog_boost:
                return "{emoji} ***Boosted***".format(emoji=self.bot.custom_emoji.get('foggy', '\U0001F301'))
            elif self.weather == "cloudy" and type in cloudy_boost:
                return "{emoji} ***Boosted***".format(emoji=self.bot.custom_emoji.get('cloudy', '\u2601'))
            elif self.weather == "partlycloudy" and type in partlycloudy_boost:
                return "{emoji} ***Boosted***".format(emoji=self.bot.custom_emoji.get('partlycloudy', '\u26C5'))
            elif self.weather == "rainy" and type in rainy_boost:
                return "{emoji} ***Boosted***".format(emoji=self.bot.custom_emoji.get('rainy', '\u2614'))
            elif self.weather == "snowy" and type in snow_boost:
                return "{emoji} ***Boosted***".format(emoji=self.bot.custom_emoji.get('snowy', '\u2744'))
            elif self.weather == "windy" and type in windy_boost:
                return "{emoji} ***Boosted***".format(emoji=self.bot.custom_emoji.get('windy', '\U0001F343'))
        return False

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
            if round(v, 3) >= 1:
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
        form = str(self.form).lower()
        if self.alolan:
            form = "alolan"
        return self.bot.pkmn_info[utils.get_name(self.bot, self.id)]['forms'][form]['type']

    def _get_emoji(self):
        """:class:`list` : Returns the Pokemon's type emoji"""
        types = self._get_type()
        ret = ""
        for type in types:
            emoji = None
            try:
                emoji_id = ''.join(x for x in self.bot.config.type_id_dict[type.lower()].split(":")[2] if x.isdigit())
                emoji = discord.utils.get(self.bot.emojis, id=int(emoji_id))
                if emoji:
                    ret += str(emoji)
                    continue
                emoji_name = self.bot.config.type_id_dict[type.lower()].split(":")[1]
                emoji = discord.utils.get(self.bot.emojis, name=emoji_name)
                if emoji:
                    ret += str(emoji)
                    continue
                else:
                    ret += f":{type.lower()}:"
            except (IndexError, ValueError):
                ret += f":{type.lower()}:"
        return ret

    def _get_cp(self, level, attack, defense, stamina):
        if not all([self.base_attack, self.base_defense, self.base_stamina]):
            return None
        if level == 15:
            cpm = 0.51739395
        elif level == 20:
            cpm = 0.5974
        elif level == 25:
            cpm = 0.667934
        elif level == 40:
            cpm = 0.7903
        attack = (self.base_attack + attack)*cpm
        defense = (self.base_defense + defense)*cpm
        stamina = (self.base_stamina + stamina)*cpm
        cp = floor((attack*defense**0.5*stamina**0.5)/10)
        if cp < 10:
            cp = 10
        return cp

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

    def query_pokemon(bot, argument):
        argument = str(argument)
        shiny = re.search(r'\bshiny\b', argument, re.IGNORECASE)
        alolan = re.search(r'\balolan*\b', argument, re.IGNORECASE)
        male = re.search(r'\b(?<!fe)male\b', argument, re.IGNORECASE)
        female = re.search(r'\bfemale\b', argument, re.IGNORECASE)
        large = re.search(r'\blarge\b|\bbig\b|\bxl\b', argument, re.IGNORECASE)
        small = re.search(r'\bsmall\b|\btiny\b|xs\b', argument, re.IGNORECASE)
        form_list = bot.form_dict['list']
        try:
            form_list.remove("none")
        except ValueError:
            pass
        pokemon = False
        match_list = []
        if shiny:
            match_list.append(shiny.group(0))
            argument = re.sub(shiny.group(0), '', argument, count=0, flags=re.IGNORECASE).strip()
            shiny = True
        else:
            shiny = False
        if alolan:
            match_list.append(alolan.group(0))
            argument = re.sub(alolan.group(0), '', argument, count=0, flags=re.IGNORECASE).strip()
            alolan = True
        else:
            alolan = False
        if male:
            match_list.append(male.group(0))
            argument = re.sub(male.group(0), '', argument, count=0, flags=re.IGNORECASE).strip()
            gender = "male"
        elif female:
            match_list.append(female.group(0))
            argument = re.sub(female.group(0), '', argument, count=0, flags=re.IGNORECASE).strip()
            gender = "female"
        else:
            gender = None
        if large:
            size = "XL"
            match_list.append(large.group(0))
            argument = re.sub(large.group(0), '', argument, count=0, flags=re.IGNORECASE).strip()
        elif small:
            size = "XS"
            match_list.append(small.group(0))
            argument = re.sub(small.group(0), '', argument, count=0, flags=re.IGNORECASE).strip()
        else:
            size = None

        for form in form_list:
            form = re.search(r"\b"+re.escape(form)+r"\b", argument, re.IGNORECASE)
            if form:
                match_list.append(form.group(0))
                argument = re.sub(form.group(0), '', argument, count=1, flags=re.IGNORECASE).strip()
                form = form.group(0).lower().strip()
                break
            else:
                form = None

        return {"argument":argument, "match_list":match_list, "shiny":shiny, "alolan":alolan, "gender":gender, "size":size, "form":form}

    @classmethod
    async def convert(self, ctx, argument):
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
        query =  self.query_pokemon(ctx.bot, argument)
        argument = query['argument']
        match = False
        for word in argument.split():
            if word.lower() not in ctx.bot.pkmn_list and not word.isdigit() and word.lower() not in ctx.bot.form_dict['two_words']:
                match, score = utils.get_match(ctx.bot.pkmn_list, word)
                if not score or score < 80:
                    argument = argument.replace(word, '').strip()
                elif "nidoran" in word.lower():
                    if query['gender'] == "female":
                        match = utils.get_name(ctx.bot, 29)
                    else:
                        match = utils.get_name(ctx.bot, 32)
                    argument = argument.replace(word, match).strip()
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
        elif not match:
            match, score = utils.get_match(ctx.bot.pkmn_list, argument)
        result = False
        if match:
            if score >= 80:
                result = self(ctx.bot, str(match), ctx.guild, shiny=query['shiny'], alolan=query['alolan'], form=query['form'], gender=query['gender'], size=query['size'])
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
    def get_pokemon(self, bot, argument, allow_digits = True):
        query =  self.query_pokemon(bot, str(argument).strip())
        argument = query['argument']
        match = False
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
        if match and "nidoran" in match.lower():
            if query['gender'] == "female":
                match = utils.get_name(bot, 29)
            else:
                match = utils.get_name(bot, 32)
        if not match:
            return None
        pokemon = self(bot, str(match), None, shiny=query['shiny'], alolan=query['alolan'], form=query['form'], gender=query['gender'], size=query['size'])
        return pokemon

    @classmethod
    async def async_get_pokemon(self, bot, argument, allow_digits = True):
        query =  self.query_pokemon(bot, str(argument).strip())
        argument = query['argument']
        match = False
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
        if match and "nidoran" in match.lower():
            if query['gender'] == "female":
                match = utils.get_name(bot, 29)
            else:
                match = utils.get_name(bot, 32)
        if not match:
            return None
        pokemon = self(bot, str(match), None, shiny=query['shiny'], alolan=query['alolan'], form=query['form'], gender=query['gender'], size=query['size'])
        return pokemon

    @classmethod
    async def ask_pokemon(self, ctx, argument, allow_digits = True, ask_correct = True):
        query =  self.query_pokemon(ctx.bot, str(argument).strip())
        argument = query['argument']
        match_list = query['match_list']
        match = False
        pokemon = False
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
                    elif "nidoran" in word.lower():
                        if query['gender'] == "female":
                            match = utils.get_name(ctx.bot, 29)
                        else:
                            match = utils.get_name(ctx.bot, 32)
                        match_list.append(word)
                        argument = argument.replace(word, match).strip()
                        pokemon = match
                    elif ask_correct:
                        match = await utils.autocorrect(ctx.bot, word, ctx.bot.pkmn_list, ctx.channel, ctx.author)
                        if not match:
                            return None, None
                        match_list.append(word)
                        argument = argument.replace(word, match).strip()
                        pokemon = match

        if not argument:
            return None, None

        if not match:
            if argument.isdigit() and allow_digits:
                match = utils.get_name(ctx.bot, int(argument))
            else:
                match = utils.get_match(ctx.bot.pkmn_list, argument.split()[0])[0]

        if not match:
            return None, None

        pokemon = self(ctx.bot, str(match), ctx.guild, shiny=query['shiny'], alolan=query['alolan'], form=query['form'], gender=query['gender'], size=query['size'])

        return pokemon, match_list

class Pokedex(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @checks.is_manager()
    async def pkmn_json(self, ctx, *, pokemon: Pokemon=None):
        """Edits pkmn.json pokemon availability

        Usage: !pkmn_json [pokemon]"""
        message = ctx.message
        channel = message.channel
        author = message.author
        guild = message.guild
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[guild.id]['configure_dict']['settings']['offset']))
        error = False
        first = True
        action = "edit"
        owner = self.bot.get_user(self.bot.owner)
        pkmn_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/pokemonstorageupgrade.1.png?cache=1')
        pkmn_embed.set_footer(text=_('Sent by @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        def check(reply):
            if reply.author is not guild.me and reply.channel.id == channel.id and reply.author == message.author:
                return True
            else:
                return False
        while True:
            async with ctx.typing():
                if not pokemon:
                    pkmn_embed.clear_fields()
                    pkmn_embed.add_field(name=_('**Edit Pokemon Information**'), value=f"{'Meowth! I will help you edit Pokemon information!' if first else ''}\n\n{'First' if first else 'Meowth! Now'}, I'll need to know what **pokemon** you'd like to edit. Reply with **name** of the pokemon and include any **form** if applicable. You can reply with **cancel** to stop anytime.", inline=False)
                    pkmn_name_wait = await channel.send(embed=pkmn_embed)
                    try:
                        pkmn_name_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        pkmn_name_msg = None
                    await utils.safe_delete(pkmn_name_wait)
                    if not pkmn_name_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(pkmn_name_msg)
                    if pkmn_name_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    else:
                        pokemon, match_list = await Pokemon.ask_pokemon(ctx, pkmn_name_msg.clean_content.lower(), allow_digits=False)
                        if not pokemon:
                            error = _("entered an invalid pokemon")
                            break
                    first = False
                if pokemon:
                    if pokemon.form:
                        pkmn_form = pokemon.form
                    else:
                        pkmn_form = "none"
                    if pokemon.alolan:
                        pkmn_form = "alolan"
                    pkmn_available = False
                    form_str = f" I only know about the {str(pokemon)} without a form."
                    if self.bot.pkmn_info.get(pokemon.name.lower(), {}).get('forms', {}).get(pkmn_form, {}).get('available', False):
                        pkmn_available = True
                    if len(self.bot.form_dict.get(pokemon.id, {}).keys()) > 1:
                        form_str = f" Current {pokemon.name} forms include: `{(', ').join(self.bot.form_dict.get(pokemon.id, {}).keys())}`"
                    pkmn_shiny = []
                    pkmn_shiny = self.bot.shiny_dict.get(pokemon.id, {}).get(pkmn_form, [])
                    pkmn_gender = False
                    if pkmn_form in self.bot.gender_dict.get(pokemon.id, []):
                        pkmn_gender = True
                    pkmn_size = False
                    if pkmn_form in self.bot.size_dict.get(pokemon.id, []):
                        pkmn_size = True
                    pkmn_embed.clear_fields()
                    pkmn_embed.add_field(name=_('**Edit Pokemon Information**'), value=f"You are now editing **{str(pokemon)}**, if this doesn't seem correct, that form may not exist. Please ask **{owner.name}** to make changes.{form_str}\n\nOtherwise, I'll need to know what **attribute** of the **{str(pokemon)}** you'd like to edit. Reply with **available** to toggle in-game availability, **shiny** to set shiny availability, **gender** to toggle gender differences, or **size** to toggle size relevance. You can reply with **cancel** to stop anytime.\n\n**Current {str(pokemon)} Settings**\nAvailable in-game: {pkmn_available}\nShiny available: {pkmn_shiny}\nGender Differences: {pkmn_gender}\nSize Relevant: {pkmn_size}", inline=False)
                    attr_type_wait = await channel.send(embed=pkmn_embed)
                    try:
                        attr_type_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        attr_type_msg = None
                    await utils.safe_delete(attr_type_wait)
                    if not attr_type_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(attr_type_msg)
                    if attr_type_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif attr_type_msg.clean_content.lower() == "gender":
                        pkmn_gender = not pkmn_gender
                        break
                    elif attr_type_msg.clean_content.lower() == "size":
                        pkmn_size = not pkmn_size
                        break
                    elif attr_type_msg.clean_content.lower() == "available":
                        pkmn_available = not pkmn_available
                        break
                    elif attr_type_msg.clean_content.lower() == "shiny":
                        pkmn_embed.clear_fields()
                        pkmn_embed.add_field(name=_('**Edit Pokemon Information**'), value=f"Shiny **{str(pokemon)}** is {'not currently available' if not pkmn_shiny else 'currently available in the following: '+str(pkmn_shiny)}.\n\nTo change availability, reply with a comma separated list of all possible occurrences that shiny {str(pokemon)} can appear in-game. You can reply with **cancel** to stop anytime.\n\nSelect from the following options:\n**hatch, raid, wild, research, nest, evolution, none**", inline=False)
                        shiny_type_wait = await channel.send(embed=pkmn_embed)
                        try:
                            shiny_type_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            shiny_type_msg = None
                        await utils.safe_delete(shiny_type_wait)
                        if not shiny_type_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(shiny_type_msg)
                        if shiny_type_msg.clean_content.lower() == "cancel":
                            error = _("cancelled the report")
                            break
                        else:
                            shiny_options = ["hatch", "raid", "wild", "research", "nest", "evolution"]
                            shiny_split = shiny_type_msg.clean_content.lower().split(',')
                            shiny_split = [x.strip() for x in shiny_split]
                            shiny_split = [x for x in shiny_split if x in shiny_options]
                            pkmn_shiny = shiny_split
                            break
                        first = False
                    else:
                        error = _("entered an invalid option")
                        break
                    first = False
        if error:
            pkmn_embed.clear_fields()
            pkmn_embed.add_field(name=_('**Pokemon Edit Cancelled**'), value=_("Meowth! Your edit has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await channel.send(embed=pkmn_embed, delete_after=10)
            await utils.safe_delete(message)
        else:
            with open(self.bot.pkmn_info_path, 'r', encoding="utf8") as fd:
                pkmn_info = json.load(fd)
            pkmn_info[pokemon.name.lower()]['forms'][pkmn_form]['available'] = pkmn_available
            pkmn_info[pokemon.name.lower()]['forms'][pkmn_form]['gender'] = pkmn_gender
            pkmn_info[pokemon.name.lower()]['forms'][pkmn_form]['shiny'] = pkmn_shiny
            pkmn_info[pokemon.name.lower()]['forms'][pkmn_form]['size'] = pkmn_size
            with open(self.bot.pkmn_info_path, 'w', encoding="utf8") as fd:
                json.dump(pkmn_info, fd, indent=2, separators=(', ', ': '))
            await Pokemon.generate_lists(self.bot)
            pkmn_embed.clear_fields()
            pkmn_embed.add_field(name=_('**Pokemon Edit Completed**'), value=f"Meowth! Your edit completed successfully.\n\n**Current {str(pokemon)} Settings**:\nAvailable in-game: {pkmn_available}\nShiny available: {pkmn_shiny}\nGender Differences: {pkmn_gender}\nSize Relevant: {pkmn_size}", inline=False)
            confirmation = await channel.send(embed=pkmn_embed)
            await utils.safe_delete(message)

    @commands.command(hidden=True)
    async def sprite(self, ctx, *, sprite: Pokemon):
        """Displays a pokemon sprite

        Usage: !sprite <pokemon with form, gender, etc>"""
        preview_embed = discord.Embed(colour=utils.colour(ctx.guild))
        preview_embed.set_image(url=sprite.img_url)
        sprite_msg = await ctx.send(embed=preview_embed)

    @commands.group(hidden=True, aliases=['dex'], invoke_without_command=True, case_insensitive=True)
    async def pokedex(self, ctx, *, pokemon: Pokemon):
        """Pokedex information for a pokemon

        Usage: !pokedex <pokemon with form, gender, etc>"""
        preview_embed = discord.Embed(colour=utils.colour(ctx.guild))
        pokemon.gender = False
        pokemon.size = None
        key_needed = False
        forms = [x.title() for x in ctx.bot.pkmn_info[pokemon.name.lower()]['forms'].keys()]
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
        preview_embed.add_field(name=f"{str(pokemon)} - #{pokemon.id} - {pokemon.emoji}", value=pokemon.pokedex, inline=False)
        if len(forms) > 1 or key_needed:
            preview_embed.add_field(name=f"{pokemon.name.title()} Forms:", value=", ".join(form_list), inline=True)
        if len(ctx.bot.pkmn_info[pokemon.name.lower()]["evolution"].split("→")) > 1:
            preview_embed.add_field(name=f"{pokemon.name.title()} Evolution:", value=ctx.bot.pkmn_info[pokemon.name.lower()]["evolution"])
        if pokemon.id in ctx.bot.legendary_list or pokemon.id in ctx.bot.mythical_list:
            preview_embed.add_field(name=f"{pokemon.name.title()} Rarity:", value=f"{'Mythical' if pokemon.id in ctx.bot.mythical_list else 'Legendary'}")
        if all([pokemon.research_cp, pokemon.raid_cp, pokemon.boost_raid_cp, pokemon.max_cp]):
            preview_embed.add_field(name=f"{pokemon.name.title()} CP by Level (Raids / Research):", value=f"15: **{pokemon.research_cp}** | 20: **{pokemon.raid_cp}** | 25: **{pokemon.boost_raid_cp}** | 40: **{pokemon.max_cp}**")
        preview_embed.set_thumbnail(url=pokemon.img_url)
        if key_needed:
            preview_embed.set_footer(text="S = Shiny Available | G = Gender Differences")
        pokedex_msg = await ctx.send(embed=preview_embed)

    @pokedex.command(hidden=True)
    async def stats(self, ctx, *, pokemon: Pokemon):
        """Detailed Pokedex information for a pokemon

        Usage: !pokedex stats <pokemon with form, gender, etc>"""
        preview_embed = discord.Embed(colour=utils.colour(ctx.guild))
        pokemon.gender = False
        pokemon.size = None
        key_needed = False
        forms = [x.title() for x in ctx.bot.pkmn_info[pokemon.name.lower()]['forms'].keys()]
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
        preview_embed.add_field(name=f"{str(pokemon)} - #{pokemon.id} - {pokemon.emoji}", value=pokemon.pokedex, inline=False)
        if len(forms) > 1 or key_needed:
            preview_embed.add_field(name=f"{pokemon.name.title()} Forms:", value=", ".join(form_list), inline=True)
        if len(ctx.bot.pkmn_info[pokemon.name.lower()]["evolution"].split("→")) > 1:
            preview_embed.add_field(name=f"{pokemon.name.title()} Evolution:", value=ctx.bot.pkmn_info[pokemon.name.lower()]["evolution"])
        if pokemon.id in ctx.bot.legendary_list or pokemon.id in ctx.bot.mythical_list:
            preview_embed.add_field(name=f"{pokemon.name.title()} Rarity:", value=f"{'Mythical' if pokemon.id in ctx.bot.mythical_list else 'Legendary'}")
        if all([pokemon.research_cp, pokemon.raid_cp, pokemon.boost_raid_cp, pokemon.max_cp]):
            preview_embed.add_field(name=f"{pokemon.name.title()} CP by Level (Raids / Research):", value=f"15: **{pokemon.research_cp}** | 20: **{pokemon.raid_cp}** | 25: **{pokemon.boost_raid_cp}** | 40: **{pokemon.max_cp}**")
        if all([pokemon.base_stamina, pokemon.base_attack, pokemon.base_defense]):
            preview_embed.add_field(name="Base Stats", value=f"Attack: **{pokemon.base_attack}** | Defense: **{pokemon.base_defense}** | Stamina: **{pokemon.base_stamina}**\n")
        field_value = ""
        if pokemon.height and pokemon.weight:
            field_value += f"Height: **{round(pokemon.height, 3)}m** | Weight: **{round(pokemon.weight, 3)}kg**\n"
        if pokemon.evolves:
            field_value += f"Evolution Candy: **{pokemon.evolve_candy}**\n"
        if pokemon.buddy_distance:
            field_value += f"Buddy Distance: **{pokemon.buddy_distance}km**\n"
        if pokemon.charge_moves and pokemon.quick_moves:
            charge_moves = [x.replace('_', ' ').title() for x in pokemon.charge_moves]
            quick_moves = [x.replace('_', ' ').title() for x in pokemon.quick_moves]
            field_value += f"Quick Moves: **{(', ').join(quick_moves)}**\nCharge Moves: **{(', ').join(charge_moves)}**"
        preview_embed.add_field(name="Other Info:", value=field_value)
        preview_embed.set_thumbnail(url=pokemon.img_url)
        if key_needed:
            preview_embed.set_footer(text="S = Shiny Available | G = Gender Differences")
        pokedex_msg = await ctx.send(embed=preview_embed)

def setup(bot):
    bot.add_cog(Pokedex(bot))

def teardown(bot):
    bot.remove_cog(Pokedex)
