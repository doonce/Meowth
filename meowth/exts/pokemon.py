
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
    bot: :class:`meowth.bot`
        Current instance of Meowth
    """

    __slots__ = ('name', 'id', 'types', 'emoji', 'bot', 'guild', 'pkmn_list',
                 'pb_raid', 'weather', 'moveset', 'form', 'region', 'shiny',
                 'gender', 'size', 'legendary', 'mythical', 'base_stamina',
                 'base_attack', 'base_defense', 'charge_moves', 'quick_moves',
                 'height', 'weight', 'evolves', 'evolve_candy', 'buddy_distance',
                 'research_cp', 'raid_cp', 'boost_raid_cp', 'max_cp', 'weather',
                 'shadow')

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
        self.region = attribs.get('region', None)
        if self.form not in bot.form_dict.get(self.id, {}):
            self.form = None
        self.gender = self.is_gender(attribs)
        self.shadow = self.is_shadow(attribs)
        self.shiny = self.is_shiny(attribs)
        self.legendary = bot.pkmn_info[self.name.lower()].get('legendary', False)
        self.mythical = bot.pkmn_info[self.name.lower()].get('mythical', False)
        self.types = self._get_type()
        self.emoji = self._get_emoji()
        self.weather = None
        self.base_stamina = self.game_template.get('pokemonSettings', {}).get('stats', {}).get('baseStamina', None)
        self.base_attack = self.game_template.get('pokemonSettings', {}).get('stats', {}).get('baseAttack', None)
        self.base_defense = self.game_template.get('pokemonSettings', {}).get('stats', {}).get('baseDefense', None)
        self.charge_moves = self.game_template.get('pokemonSettings', {}).get('cinematicMoves', None)
        if self.charge_moves:
            self.charge_moves = [x.replace('_FAST', '').replace('_', ' ').lower() for x in self.charge_moves]
        self.quick_moves = self.game_template.get('pokemonSettings', {}).get('quickMoves', None)
        if self.quick_moves:
            self.quick_moves = [x.replace('_FAST', '').replace('_', ' ').lower() for x in self.quick_moves]
        self.height = self.game_template.get('pokemonSettings', {}).get('pokedexHeightM', None)
        self.weight = self.game_template.get('pokemonSettings', {}).get('pokedexWeightKg', None)
        self.evolves = self.game_template.get('pokemonSettings', {}).get('evolutionIds', False) or self.game_template.get('pokemonSettings', {}).get('evolutionBranch', False)
        self.evolve_candy = self.game_template.get('pokemonSettings', {}).get('evolutionBranch', [{}])[0].get('candyCost', False) or self.game_template.get('pokemonSettings', {}).get('candyToEvolve', False)
        self.buddy_distance = self.game_template.get('pokemonSettings', {}).get('kmBuddyDistance', None)
        self.research_cp = f"{self._get_cp(15, 10, 10, 10)}-{self._get_cp(15, 15, 15, 15)}"
        self.raid_cp = f"{self._get_cp(20, 10, 10, 10)}-{self._get_cp(20, 15, 15, 15)}"
        self.boost_raid_cp = f"{self._get_cp(25, 10, 10, 10)}-{self._get_cp(25, 15, 15, 15)}"
        self.max_cp = f"{self._get_cp(40, 10, 10, 10)}-{self._get_cp(40, 15, 15, 15)}"

    def __str__(self):
        name = self.name.title()
        size = ""
        region = ""
        form = ""
        shadow = ""
        shiny = ""
        gender = ""
        if self.size:
            size = f"{self.size}"
        if self.region == "alolan":
            region = f"Alolan"
        elif self.region == "galarian":
            region = f"Galarian"
        if self.form:
            form = f"{self.form.title()}"
        if self.shadow:
            shadow = f"{self.shadow.title()}"
        if self.shiny:
            shiny = f"Shiny"
        if self.gender:
            gender = str(self.gender).title()
        modifier_list = [gender, shiny, shadow, region, size, name, form]
        pkmn_str = (' ').join([x for x in modifier_list if x])
        return pkmn_str

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
        if self.region:
            if self.form:
                pkmn_form = f"{self.region} {self.form}"
            else:
                pkmn_form = self.region
        else:
            if self.form:
                pkmn_form = self.form
            else:
                pkmn_form = "none"
        if self.gender:
            return self.bot.pkmn_info[pkmn_name]['forms'][pkmn_form]['gender'][self.gender]['pokedex']
        else:
            return self.bot.pkmn_info[pkmn_name]['forms'][pkmn_form]['pokedex']

    @property
    def evolution(self):
        """:class:`str` : Pokemon Evolution Entry"""
        pkmn_name = str(self.name).lower()
        if self.region:
            if self.form:
                pkmn_form = f"{self.region} {self.form}"
            else:
                pkmn_form = self.region
        else:
            if self.form:
                pkmn_form = self.form
            else:
                pkmn_form = "none"
        if self.gender:
            return self.bot.pkmn_info[pkmn_name]['forms'][pkmn_form]['gender'][self.gender]['evolution']
        else:
            return self.bot.pkmn_info[pkmn_name]['forms'][pkmn_form]['evolution']

    @property
    def shiny_available(self):
        """:class:`list` : Pokemon shiny available"""
        pkmn_name = str(self.name).lower()
        if self.region:
            if self.form:
                pkmn_form = f"{self.region} {self.form}"
            else:
                pkmn_form = self.region
        else:
            if self.form:
                pkmn_form = self.form
            else:
                pkmn_form = "none"
        return self.bot.pkmn_info[pkmn_name]['forms'][pkmn_form].get('shiny', False)

    def is_shiny(self, attributes):
        shiny = dict(attributes).get('shiny', False)
        if shiny and self.shiny_available:
            return True
        return False

    @property
    def shadow_available(self):
        """:class:`bool` : Pokemon shadow available"""
        pkmn_name = str(self.name).lower()
        if self.region:
            if self.form:
                pkmn_form = f"{self.region} {self.form}"
            else:
                pkmn_form = self.region
        else:
            if self.form:
                pkmn_form = self.form
            else:
                pkmn_form = "none"
        return self.bot.pkmn_info[pkmn_name]['forms'][pkmn_form].get('shadow', False)

    def is_shadow(self, attributes):
        shadow = dict(attributes).get('shadow', False)
        if shadow and self.shadow_available:
            return shadow
        return False

    @property
    def size_available(self):
        """:class:`bool` : Pokemon size available"""
        pkmn_name = str(self.name).lower()
        if self.region:
            if self.form:
                pkmn_form = f"{self.region} {self.form}"
            else:
                pkmn_form = self.region
        else:
            if self.form:
                pkmn_form = self.form
            else:
                pkmn_form = "none"
        return self.bot.pkmn_info[pkmn_name]['forms'][pkmn_form].get('size', False)

    def is_size(self, attributes):
        size = dict(attributes).get('size', False)
        if size and self.size_available:
            return size
        return None

    @property
    def gender_available(self):
        """:class:`bool` : Pokemon gender available"""
        pkmn_name = str(self.name).lower()
        if self.region:
            if self.form:
                pkmn_form = f"{self.region} {self.form}"
            else:
                pkmn_form = self.region
        else:
            if self.form:
                pkmn_form = self.form
            else:
                pkmn_form = "none"
        return self.bot.pkmn_info[pkmn_name]['forms'][pkmn_form].get('gender', False)

    def is_gender(self, attributes):
        gender = dict(attributes).get('gender', False)
        if gender and self.gender_available:
            return gender
        return None

    @property
    def img_url(self):
        """:class:`str` : Pokemon sprite image URL"""
        pkmn_no = str(self.id).zfill(3)
        gender_str = ""
        form_str = ""
        region_str = ""
        shiny_str = ""
        shadow_str = ""
        region_list = ["alolan", "galarian"]
        if self.gender == "female":
            gender_str = "_01"
        elif self.gender == "male":
            gender_str = "_00"
        if self.region == "alolan":
            region_str = "_61"
        elif self.region == "galarian":
            region_str = "_31"
        if self.form:
            form_list = [x for x in list(self.bot.pkmn_info[self.name.lower()]['forms'].keys()) if x not in region_list]
            form_index = form_list.index(f"{self.region+' ' if self.region else ''}{str(self.form).lower()}")
            form_str = f"{region_str}_{str(form_index).zfill(2)}"
        elif self.region:
            form_str = region_str
        if self.shiny:
            shiny_str = "_shiny"
        if self.shadow:
            shadow_str = f"_{self.shadow}"
        if not self.gender and not self.form and not self.region:
            form_str = "_00"
        return (f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/pkmn_icons/pokemon_icon_{pkmn_no}{gender_str}{form_str}{shiny_str}.png?cache=2")

    @property
    def game_name(self):
        template = {}
        name = self.name
        if self.id == 250:
            name = "ho_oh"
        search_term = f"{name}".lower()
        excluded_forms = list(self.bot.pkmn_info['pikachu']['forms'].keys()) + ["sunglasses"]
        if self.id == 201:
            excluded_forms.extend(list(self.bot.pkmn_info['unown']['forms'].keys()))
        elif self.id == 327:
            excluded_forms.extend(list(self.bot.pkmn_info['spinda']['forms'].keys()))
        form = None
        if self.form == "armored":
            form = "a"
        elif self.region == "alolan":
            form = "alola"
        if self.shadow:
            form = self.shadow
        if form and form not in excluded_forms:
            search_term = f"{name}_{str(form).strip()}".lower()
        return search_term

    @property
    def game_template(self):
        template = {}
        search_term = f"V{str(self.id).zfill(4)}_pokemon_{self.game_name}".lower()
        for template in self.bot.gamemaster.get('itemTemplates', {}):
            if search_term in template['templateId'].lower() and "forms_" not in template['templateId'].lower() and "spawn_" not in template['templateId'].lower() and "pokemon" in template['templateId'].lower():
                break
        return template

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
        return utils.get_level(self.bot, str(self))

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
                return "{emoji} ***Boosted***".format(emoji=self.bot.custom_emoji.get('clear', u'\U00002600\U0000fe0f'))
            elif self.weather == "foggy" and type in fog_boost:
                return "{emoji} ***Boosted***".format(emoji=self.bot.custom_emoji.get('foggy', u'\U0001f32b\U0000fe0f'))
            elif self.weather == "cloudy" and type in cloudy_boost:
                return "{emoji} ***Boosted***".format(emoji=self.bot.custom_emoji.get('cloudy', u'\U00002601\U0000fe0f'))
            elif self.weather == "partlycloudy" and type in partlycloudy_boost:
                return "{emoji} ***Boosted***".format(emoji=self.bot.custom_emoji.get('partlycloudy', u'\U0001f325\U0000fe0f'))
            elif self.weather == "rainy" and type in rainy_boost:
                return "{emoji} ***Boosted***".format(emoji=self.bot.custom_emoji.get('rainy', u'\U0001f327\U0000fe0f'))
            elif self.weather == "snowy" and type in snow_boost:
                return "{emoji} ***Boosted***".format(emoji=self.bot.custom_emoji.get('snowy', u'\U00002744\U0000fe0f'))
            elif self.weather == "windy" and type in windy_boost:
                return "{emoji} ***Boosted***".format(emoji=self.bot.custom_emoji.get('windy', u'\U0001F343'))
        return False

    @property
    def boost_weather(self):
        weather_boost = []
        windy_emoji = self.bot.config.custom_emoji.get('windy', u"\U0001F343")
        windy_boost = ["Dragon", "Flying", "Psychic"]
        snowy_emoji = self.bot.config.custom_emoji.get('snowy', u"\U00002744\U0000fe0f")
        snowy_boost = ["Ice", "Steel"]
        partlycloudy_emoji = self.bot.config.custom_emoji.get('partlycloudy', u"\U0001f325\U0000fe0f")
        partlycloudy_boost = ["Normal", "Rock"]
        foggy_emoji = self.bot.config.custom_emoji.get('foggy', u"\U0001f32b\U0000fe0f")
        foggy_boost = ["Dark", "Ghost"]
        cloudy_emoji = self.bot.config.custom_emoji.get('cloudy', u"\U00002601\U0000fe0f")
        cloudy_boost = ["Fairy", "Fighting", "Poison"]
        rainy_emoji = self.bot.config.custom_emoji.get('rainy', u"\U0001f327\U0000fe0f")
        rainy_boost = ["Water", "Electric", "Bug"]
        clear_emoji = self.bot.config.custom_emoji.get('clear', u"\U00002600\U0000fe0f")
        clear_boost = ["Fire", "Grass", "Ground"]
        for type in self.types:
            if type in windy_boost and windy_emoji not in weather_boost:
                weather_boost.append(windy_emoji)
            elif type in snowy_boost and snowy_emoji not in weather_boost:
                weather_boost.append(snowy_emoji)
            elif type in partlycloudy_boost and partlycloudy_emoji not in weather_boost:
                weather_boost.append(partlycloudy_emoji)
            elif type in foggy_boost and foggy_emoji not in weather_boost:
                weather_boost.append(foggy_emoji)
            elif type in cloudy_boost and cloudy_emoji not in weather_boost:
                weather_boost.append(cloudy_emoji)
            elif type in rainy_boost and rainy_emoji not in weather_boost:
                weather_boost.append(rainy_emoji)
            elif type in clear_boost and clear_emoji not in weather_boost:
                weather_boost.append(clear_emoji)
        return weather_boost

    def set_guild(self, guild):
        """:class:`discord.Guild` or :obj:`None` : Sets the relevant Guild"""
        self.guild = guild

    @property
    def weakness_dict(self):
        return utils.get_weaknesses(self.bot, self.types)

    @property
    def weakness_emoji(self):
        return utils.weakness_to_emoji(self.bot, self.weakness_dict)

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
        if self.region:
            if self.form:
                pkmn_form = f"{self.region} {self.form}"
            else:
                pkmn_form = self.region
        else:
            if self.form:
                pkmn_form = self.form
            else:
                pkmn_form = "none"
        if self.gender:
            return self.bot.pkmn_info[utils.get_name(self.bot, self.id)]['forms'][pkmn_form]['gender'][self.gender]['type']
        else:
            return self.bot.pkmn_info[utils.get_name(self.bot, self.id)]['forms'][pkmn_form]['type']

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
        modifier_dict = {
            "15": 0.51739395,
            "20": 0.5974,
            "25": 0.667934,
            "40": 0.7903
        }
        cpm = modifier_dict.get(str(level), 0)
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
        alolan = re.search(r'\balola\b|\balolan\b', argument, re.IGNORECASE)
        galarian = re.search(r'\bgalar\b|\bgalarian\b', argument, re.IGNORECASE)
        male = re.search(r'\b(?<!fe)male\b', argument, re.IGNORECASE)
        female = re.search(r'\bfemale\b', argument, re.IGNORECASE)
        large = re.search(r'\blarge\b|\bbig\b|\bxl\b', argument, re.IGNORECASE)
        small = re.search(r'\bsmall\b|\btiny\b|xs\b', argument, re.IGNORECASE)
        shadow = re.search(r'\bshadow\b', argument, re.IGNORECASE)
        purified = re.search(r'\bpurified\b', argument, re.IGNORECASE)
        match_list = []
        form_list = []
        shiny = False
        if shiny:
            match_list.append(shiny.group(0))
            argument = re.sub(shiny.group(0), '', argument, count=0, flags=re.IGNORECASE).strip()
            shiny = True
        shadow = False
        if shadow:
            match_list.append(shadow.group(0))
            argument = re.sub(shadow.group(0), '', argument, count=0, flags=re.IGNORECASE).strip()
            shadow = "shadow"
        elif purified:
            match_list.append(purified.group(0))
            argument = re.sub(purified.group(0), '', argument, count=0, flags=re.IGNORECASE).strip()
            shadow = "purified"
        gender = None
        if male:
            match_list.append(male.group(0))
            argument = re.sub(male.group(0), '', argument, count=0, flags=re.IGNORECASE).strip()
            gender = "male"
        elif female:
            match_list.append(female.group(0))
            argument = re.sub(female.group(0), '', argument, count=0, flags=re.IGNORECASE).strip()
            gender = "female"
        size = None
        if large:
            size = "XL"
            match_list.append(large.group(0))
            argument = re.sub(large.group(0), '', argument, count=0, flags=re.IGNORECASE).strip()
        elif small:
            size = "XS"
            match_list.append(small.group(0))
            argument = re.sub(small.group(0), '', argument, count=0, flags=re.IGNORECASE).strip()
        region = None
        if alolan:
            region = "alolan"
            match_list.append(alolan.group(0))
            argument = re.sub(alolan.group(0), '', argument, count=0, flags=re.IGNORECASE).strip()
        elif galarian:
            region = "galarian"
            match_list.append(galarian.group(0))
            argument = re.sub(galarian.group(0), '', argument, count=0, flags=re.IGNORECASE).strip()
        for word in argument.lower().split():
            if word in bot.pkmn_info.keys():
                form_list.extend(list(bot.pkmn_info[word]['forms'].keys()))
        if not form_list:
            form_list = list(bot.form_dict['list'])
        argument = argument.replace("ho oh", "ho-oh").replace("jangmo o", "jangmo-o").replace("hakamo o", "hakamo-o").replace("kommo o", "kommo-o")
        form = None
        for pkmn_form in form_list:
            if pkmn_form == "alolan" or pkmn_form == "galarian" or pkmn_form == "none":
                continue
            form_search = re.search(r"\b"+re.escape(pkmn_form)+r"\b", argument, re.IGNORECASE)
            if form_search:
                match_list.append(form_search.group(0))
                argument = re.sub(form_search.group(0), '', argument, count=1, flags=re.IGNORECASE).strip()
                form = pkmn_form
                break
            else:
                form = None

        return {"argument":argument, "match_list":match_list, "shiny":shiny, "gender":gender, "size":size, "form":form, "region":region, "shadow":shadow}

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
                result = self(ctx.bot, str(match), ctx.guild, shiny=query['shiny'], form=query['form'], region=query['region'], gender=query['gender'], size=query['size'], shadow=query['shadow'])
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
    def get_pokemon(self, bot, argument, allow_digits=False):
        entered_argument = str(argument)
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

        if entered_argument.isdigit() and allow_digits:
            match = utils.get_name(bot, int(entered_argument))
        else:
            match = utils.get_match(bot.pkmn_list, argument)[0]
        if match and "nidoran" in match.lower():
            if query['gender'] == "female":
                match = utils.get_name(bot, 29)
            else:
                match = utils.get_name(bot, 32)
        if not match:
            return None
        if entered_argument.isdigit() and allow_digits:
            pokemon = self(bot, str(match), None, shiny=False, form=None, region=None, gender=None, size=None, shadow=None)
        else:
            pokemon = self(bot, str(match), None, shiny=query['shiny'], form=query['form'], region=query['region'], gender=query['gender'], size=query['size'], shadow=query['shadow'])
        return pokemon

    @classmethod
    async def async_get_pokemon(self, bot, argument, allow_digits=False):
        entered_argument = str(argument)
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
        if entered_argument.isdigit() and allow_digits:
            match = utils.get_name(bot, int(entered_argument))
        else:
            match = utils.get_match(bot.pkmn_list, argument)[0]
        if match and "nidoran" in match.lower():
            if query['gender'] == "female":
                match = utils.get_name(bot, 29)
            else:
                match = utils.get_name(bot, 32)
        if not match:
            return None
        if entered_argument.isdigit() and allow_digits:
            pokemon = self(bot, str(match), None, shiny=False, form=None, region=None, gender=None, size=None, shadow=None)
        else:
            pokemon = self(bot, str(match), None, shiny=query['shiny'], form=query['form'], region=query['region'], gender=query['gender'], size=query['size'], shadow=query['shadow'])
        return pokemon

    @classmethod
    async def ask_pokemon(self, ctx, argument, allow_digits=True, ask_correct=True):
        entered_argument = str(argument)
        query =  self.query_pokemon(ctx.bot, str(argument).strip())
        argument = query['argument']
        match_list = query['match_list']
        match = False
        pokemon = None
        possible_matches = {}
        for word in argument.split():
            if word in ctx.bot.pkmn_list:
                possible_matches[word] = {"score":100, "word":word, "index":entered_argument.find(word)}
                argument = argument.replace(word, '').strip()
            elif word.isdigit() and allow_digits:
                possible_matches[utils.get_name(ctx.bot, int(word))] = {"score":100, "word":word, "index":entered_argument.find(word)}
                argument = argument.replace(word, '').strip()
            elif word.lower() not in ctx.bot.pkmn_list and not word.isdigit() and word.lower() not in ctx.bot.form_dict['two_words']:
                match, score = utils.get_match(ctx.bot.pkmn_list, word)
                if not score or score < 80:
                    argument = argument.replace(word, '').strip()
                else:
                    argument = argument.replace(word, '').strip()
                    if match and (match not in possible_matches or score > possible_matches.get(match, {}).get('score', 0)):
                        possible_matches[match] = {"score":score, "word":word, "index":entered_argument.find(word)}
        match, score = utils.get_match(ctx.bot.pkmn_list, argument)
        if match:
            possible_matches[match] = {"score":score, "word":argument, "index":entered_argument.find(argument)}
        if not possible_matches:
            return None, None
        first_match = list(sorted(possible_matches.items(), key=lambda x: x[1]['index']))[0][0]
        top_match = list(sorted(possible_matches.items(), key=lambda x: x[1]['score'], reverse=True))[0][0]
        if first_match == top_match:
            pokemon = first_match
            match_list.append(first_match)
        else:
            match = await utils.autocorrect(ctx.bot, possible_matches[first_match]['word'], ctx.bot.pkmn_list, ctx.channel, ctx.author)
            if not match:
                return None, None
            pokemon = match
            match_list.append(match)
        if pokemon and "nidoran" in pokemon.lower():
            if query['gender'] == "female":
                pokemon = utils.get_name(ctx.bot, 29)
            else:
                pokemon = utils.get_name(ctx.bot, 32)
            match_list.append(pokemon)
        if not pokemon:
            return None, None
        if entered_argument.isdigit() and allow_digits:
            pokemon = self(ctx.bot, str(pokemon), None, shiny=False, form=None, region=None, gender=None, size=None, shadow=None)
        else:
            pokemon = self(ctx.bot, str(pokemon), None, shiny=query['shiny'], form=query['form'], region=query['region'], gender=query['gender'], size=query['size'], shadow=query['shadow'])
        return pokemon, match_list

class Pokedex(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    async def generate_lists(bot):
        form_dict = {}
        form_list = []
        two_words = []
        for k, v in bot.pkmn_info.items():
            for form in v['forms']:
                if form == "list":
                    continue
                if len(v['forms']) > 1:
                    if form not in form_list:
                        form_list.append(form)
                    if v['number'] not in form_dict:
                        form_dict[v['number']] = {}
                    form_dict[v['number']][form] = True
            if len(k.split()) > 1:
                for word in k.split():
                    two_words.append(word)
                    two_words.append(re.sub('[^a-zA-Z0-9]', '', word))
        two_words.extend(['ho', 'oh', 'o'])
        form_dict['list'] = form_list
        form_dict['two_words'] = two_words
        bot.form_dict = form_dict
        bot.gamemaster = {}
        async with aiohttp.ClientSession() as sess:
            async with sess.get("https://raw.githubusercontent.com/pokemongo-dev-contrib/pokemongo-game-master/master/versions/latest/GAME_MASTER.json") as resp:
                data = await resp.json(content_type=None)
                bot.gamemaster = data

    @commands.command()
    @checks.is_manager()
    async def move_json(self, ctx):
        move_info = {}
        for template in self.bot.gamemaster['itemTemplates']:
            if "MOVE" in template['templateId'] and "COMBAT_" not in template['templateId'] and "ITEM_" not in template['templateId'] and "SETTINGS" not in template['templateId']:
                move_name = template['templateId'].split('MOVE_')[1].title()
                move_type = template['moveSettings']['pokemonType'].replace("POKEMON_TYPE_", "").title()
                move_power = template['moveSettings'].get('power', 0)
                move_info[move_name.lower().replace('_fast', '').replace('_', ' ')] = {"type":move_type, "power":move_power}
        for type in self.bot.type_list:
            move_info[f"hidden power {type.lower()}"] = {"type":type.title(), "power":15}
        with open(os.path.join('data', 'move_info.json'), 'w') as fd:
             json.dump(move_info, fd, indent=2, separators=(', ', ': '))
        await ctx.send(f"**{len(move_info)}** moves updated.", delete_after=15)

    @commands.command()
    @checks.is_manager()
    async def pkmn_json(self, ctx, *, pokemon: Pokemon=None):
        """Edits pkmn.json pokemon availability

        Usage: !pkmn_json [pokemon]"""
        message = ctx.message
        channel = message.channel
        author = message.author
        guild = message.guild
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        error = False
        first = True
        action = "edit"
        owner = self.bot.get_user(self.bot.owner)
        pkmn_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/pokemonstorageupgrade.1.png?cache=1')
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
                    pkmn_embed.add_field(name=_('**Edit Pokemon Information**'), value=f"{'Meowth! I will help you edit Pokemon information!' if first else ''}\n\n{'First,' if first else 'Meowth! Now,'} I'll need to know what **pokemon** you'd like to edit. Reply with **name** of the pokemon and include any **form** if applicable. You can reply with **cancel** to stop anytime.", inline=False)
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
                        pokemon, match_list = await Pokemon.ask_pokemon(ctx, pkmn_name_msg.clean_content.lower())
                        if not pokemon:
                            error = _("entered an invalid pokemon")
                            break
                    first = False
                if pokemon:
                    if pokemon.region:
                        if pokemon.form:
                            pkmn_form = f"{pokemon.region} {pokemon.form}"
                        else:
                            pkmn_form = pokemon.region
                    else:
                        if pokemon.form:
                            pkmn_form = pokemon.form
                        else:
                            pkmn_form = "none"
                    form_str = f" I only know about the {str(pokemon)} without a form."
                    if len(self.bot.form_dict.get(pokemon.id, {}).keys()) > 1:
                        form_str = f" Current {pokemon.name} forms include: `{(', ').join(self.bot.form_dict.get(pokemon.id, {}).keys())}`"
                    pkmn_shiny = pokemon.shiny_available
                    pkmn_gender = False
                    if pokemon.gender_available:
                        pkmn_gender = self.bot.pkmn_info[pokemon.name.lower()]['forms'][pkmn_form]['gender']
                    pkmn_size = False
                    if pokemon.size_available:
                        pkmn_size = True
                    pkmn_shadow = False
                    if pokemon.shadow_available:
                        pkmn_shadow = True
                    if pokemon.gender:
                        pkmn_type = self.bot.pkmn_info[pokemon.name.lower()]['forms'][pkmn_form]['gender'][pokemon.gender]['type']
                    else:
                        pkmn_type = self.bot.pkmn_info[pokemon.name.lower()]['forms'][pkmn_form]['type']
                    if pokemon.gender:
                        pkmn_dex = self.bot.pkmn_info[pokemon.name.lower()]['forms'][pkmn_form]['gender'][pokemon.gender]['pokedex']
                    else:
                        pkmn_dex = self.bot.pkmn_info[pokemon.name.lower()]['forms'][pkmn_form]['pokedex']
                    if pokemon.gender:
                        pkmn_evo = self.bot.pkmn_info[pokemon.name.lower()]['forms'][pkmn_form]['gender'][pokemon.gender]['evolution']
                    else:
                        pkmn_evo = self.bot.pkmn_info[pokemon.name.lower()]['forms'][pkmn_form]['evolution']
                    pkmn_embed.clear_fields()
                    pkmn_embed.add_field(name=_('**Edit Pokemon Information**'), value=f"You are now editing **{str(pokemon)}**, if this doesn't seem correct, that form may not exist in my records. Please ask **{owner.name}** to make changes.{form_str}\n\nOtherwise, I'll need to know what **attribute** of the **{str(pokemon)}** you'd like to edit. Reply with **shiny** to set shiny availability, **gender** to toggle gender differences, or **size** to toggle size relevance, **shadow** to toggle shadow. Others include **type**, **pokedex**, and **evolution**. You can reply with **cancel** to stop anytime.\n\n**Current {str(pokemon)} Settings**\nShiny available: {pkmn_shiny}\nGender Differences: {'True' if pkmn_gender else 'False'}\nSize Relevant: {pkmn_size}\nShadow Available: {pkmn_shadow}", inline=False)
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
                        if self.bot.pkmn_info[pokemon.name.lower()]['forms'][pkmn_form].get('gender', {}).get('male', False):
                            pkmn_gender = None
                        else:
                            pkmn_gender = {
                                "male":{
                                    "type":self.bot.pkmn_info[pokemon.name.lower()]['forms'][pkmn_form]['type'],
                                    "pokedex":self.bot.pkmn_info[pokemon.name.lower()]['forms'][pkmn_form]['pokedex'],
                                    "evolution":self.bot.pkmn_info[pokemon.name.lower()]['forms'][pkmn_form]['evolution']
                                },
                                "female":{
                                    "type":self.bot.pkmn_info[pokemon.name.lower()]['forms'][pkmn_form]['type'],
                                    "pokedex":self.bot.pkmn_info[pokemon.name.lower()]['forms'][pkmn_form]['pokedex'],
                                    "evolution":self.bot.pkmn_info[pokemon.name.lower()]['forms'][pkmn_form]['evolution']
                                }
                            }
                        break
                    elif attr_type_msg.clean_content.lower() == "size":
                        pkmn_size = not pkmn_size
                        break
                    elif attr_type_msg.clean_content.lower() == "shadow":
                        pkmn_shadow = not pkmn_shadow
                        break
                    elif attr_type_msg.clean_content.lower() == "shiny":
                        pkmn_embed.clear_fields()
                        pkmn_embed.add_field(name=_('**Edit Pokemon Information**'), value=f"Shiny **{str(pokemon)}** is {'not currently available' if not pkmn_shiny else 'currently available in the following: '+str(pkmn_shiny)}.\n\nTo change availability, reply with a comma separated list of all possible occurrences that shiny {str(pokemon)} can appear in-game. You can reply with **cancel** to stop anytime.\n\nSelect from the following options:\n**hatch, raid, wild, research, evolution, shadow, none**", inline=False)
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
                            shiny_options = ["hatch", "raid", "wild", "research", "invasion", "evolution", "shadow"]
                            shiny_split = shiny_type_msg.clean_content.lower().split(',')
                            shiny_split = [x.strip() for x in shiny_split]
                            shiny_split = [x for x in shiny_split if x in shiny_options]
                            pkmn_shiny = shiny_split
                            break
                        first = False
                    elif attr_type_msg.clean_content.lower() == "type":
                        pkmn_embed.clear_fields()
                        pkmn_embed.add_field(name=_('**Edit Pokemon Information**'), value=f"The types for **{str(pokemon)}** are **{', '.join(pkmn_type)}**\nTo change types, reply with a comma separated list of up to two types. You can reply with **cancel** to stop anytime.\n\nSelect from the following options:\n**{', '.join(self.bot.type_list)}**", inline=False)
                        type_wait = await channel.send(embed=pkmn_embed)
                        try:
                            type_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            type_msg = None
                        await utils.safe_delete(type_wait)
                        if not type_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(type_msg)
                        if type_msg.clean_content.lower() == "cancel":
                            error = _("cancelled the report")
                            break
                        else:
                            type_split = type_msg.clean_content.lower().split(',')
                            type_split = [x.strip() for x in type_split]
                            type_split = [x.title() for x in type_split if x in self.bot.type_list]
                            if len(type_split) > 2 or len(type_split) == 0:
                                error = _("entered an incorrect amount of types")
                                break
                            pkmn_type = type_split
                            break
                    elif attr_type_msg.clean_content.lower() == "pokedex":
                        pkmn_embed.clear_fields()
                        pkmn_embed.add_field(name=_('**Edit Pokemon Information**'), value=f"The pokedex entry for **{str(pokemon)}** is **{pkmn_dex}**\n\nTo change pokedex entry, reply with the text to display. You can reply with **cancel** to stop anytime.", inline=False)
                        pokedex_wait = await channel.send(embed=pkmn_embed)
                        try:
                            pokedex_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            pokedex_msg = None
                        await utils.safe_delete(pokedex_wait)
                        if not pokedex_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(pokedex_msg)
                        if pokedex_msg.clean_content.lower() == "cancel":
                            error = _("cancelled the report")
                            break
                        else:
                            pkmn_dex = pokedex_msg.clean_content
                            break
                    elif attr_type_msg.clean_content.lower() == "evolution":
                        pkmn_embed.clear_fields()
                        pkmn_embed.add_field(name=_('**Edit Pokemon Information**'), value=f"The current evolution chain for **{str(pokemon)}** is {pkmn_evo}.\n\nTo change evolution chain, reply with a comma separated list of pokemon in order. If there are multiple options at each stage, use a '/' between them. You can reply with **cancel** to stop anytime.", inline=False)
                        evolution_wait = await channel.send(embed=pkmn_embed)
                        try:
                            evolution_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            evolution_msg = None
                        await utils.safe_delete(evolution_wait)
                        if not evolution_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(evolution_msg)
                        if evolution_msg.clean_content.lower() == "cancel":
                            error = _("cancelled the report")
                            break
                        else:
                            evolution_list = []
                            evolution_split = evolution_msg.clean_content.lower().split(',')
                            evolution_split = [x.strip() for x in evolution_split]
                            if not evolution_split:
                                error = _("entered an invalid amount of evolution steps")
                                break
                            for step in evolution_split:
                                step = step.split('/')
                                step = [x.strip() for x in step]
                                step = (' / ').join(step)
                                evolution_list.append(f"[ {step.title()} ]")
                                pkmn_evo = (' \u2192  ').join(evolution_list)
                            break
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
            if pkmn_gender:
                pkmn_info[pokemon.name.lower()]['forms'][pkmn_form]['gender'] = pkmn_gender
            else:
                try:
                    del pkmn_info[pokemon.name.lower()]['forms'][pkmn_form]['gender']
                except:
                    pass
            pkmn_info[pokemon.name.lower()]['forms'][pkmn_form]['shiny'] = pkmn_shiny
            pkmn_info[pokemon.name.lower()]['forms'][pkmn_form]['size'] = pkmn_size
            pkmn_info[pokemon.name.lower()]['forms'][pkmn_form]['shadow'] = pkmn_shadow
            if pokemon.gender:
                pkmn_info[pokemon.name.lower()]['forms'][pkmn_form]['gender'][pokemon.gender]['type'] = pkmn_type
                pkmn_info[pokemon.name.lower()]['forms'][pkmn_form]['gender'][pokemon.gender]['pokedex'] = pkmn_dex
                pkmn_info[pokemon.name.lower()]['forms'][pkmn_form]['gender'][pokemon.gender]['evolution'] = pkmn_evo
            else:
                pkmn_info[pokemon.name.lower()]['forms'][pkmn_form]['type'] = pkmn_type
                pkmn_info[pokemon.name.lower()]['forms'][pkmn_form]['pokedex'] = pkmn_dex
                pkmn_info[pokemon.name.lower()]['forms'][pkmn_form]['evolution'] = pkmn_evo
            with open(self.bot.pkmn_info_path, 'w', encoding="utf8") as fd:
                json.dump(pkmn_info, fd, indent=2, separators=(', ', ': '))
            await self.generate_lists(self.bot)
            pkmn_embed.clear_fields()
            pkmn_embed.add_field(name=_('**Pokemon Edit Completed**'), value=f"Meowth! Your edit completed successfully.\n\n**Current {str(pokemon)} Settings**:\nShiny available: {pkmn_shiny}\nGender Differences: {'True' if pkmn_gender else 'False'}\nSize Relevant: {pkmn_size}\nShadow Available: {pkmn_shadow}", inline=False)
            confirmation = await channel.send(embed=pkmn_embed)
            await utils.safe_delete(message)

    @commands.group(invoke_without_command=True, case_insensitive=True)
    async def sprite(self, ctx, *, sprite: Pokemon):
        """Displays a pokemon sprite

        Usage: !sprite <pokemon with form, gender, etc>"""
        preview_embed = discord.Embed(colour=utils.colour(ctx.guild))
        preview_embed.set_image(url=sprite.img_url)
        sprite_msg = await ctx.send(embed=preview_embed)

    @sprite.command(name="img", hidden=True)
    async def sprite_img(self, ctx, *, sprite: Pokemon):
        sprite_msg = await ctx.send(sprite.img_url)

    @commands.group(aliases=['dex'], invoke_without_command=True, case_insensitive=True)
    async def pokedex(self, ctx, *, pokemon: str=None):
        """Pokedex information for a pokemon

        Usage: !pokedex <pokemon with form, gender, etc>"""
        if not pokemon and checks.check_hatchedraid(ctx):
            report_dict = await utils.get_report_dict(ctx.bot, ctx.channel)
            pokemon = self.bot.guild_dict[ctx.guild.id].setdefault(report_dict, {}).get(ctx.channel.id, {}).get('pkmn_obj', None)
        pokemon = await Pokemon.async_get_pokemon(self.bot, pokemon, allow_digits=True)
        preview_embed = discord.Embed(colour=utils.colour(ctx.guild)).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/Badge_Pokedex_GOLD_01.png?cache=1')
        error = False
        stats = False
        if not pokemon:
            while True:
                async with ctx.typing():
                    preview_embed.add_field(name=_('**Search Pokedex**'), value=_("Meowth! Welcome to my pokedex! I'll help you get information for pokemon!\n\nFirst, I'll need to know what **pokemon** you'd like information for. Reply with the name of a **pokemon** with any form, gender, etc. You can reply with **cancel** to stop anytime."), inline=False)
                    mon_wait = await ctx.channel.send(embed=preview_embed)
                    def check(reply):
                        if reply.author is not ctx.guild.me and reply.channel.id == ctx.channel.id and reply.author == ctx.message.author:
                            return True
                        else:
                            return False
                    try:
                        mon_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        mon_msg = None
                    await utils.safe_delete(mon_wait)
                    if not mon_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(mon_msg)
                    if mon_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    else:
                        pokemon = None
                        pokemon, __ = await pkmn_class.Pokemon.ask_pokemon(ctx, mon_msg.clean_content)
                        if not pokemon:
                            error = _("entered an invalid pokemon")
                            break
                        else:
                            preview_embed.set_thumbnail(url=pokemon.img_url)
                    preview_embed.clear_fields()
                    preview_embed.add_field(name=_('**Search Pokedex**'), value=f"Great! Now, would you like extra details for **{str(pokemon)}**, such as moves, height, and weight?\n\nReply with **yes** or **no**. You can reply with **cancel** to stop anytime.", inline=False)
                    mon_wait = await ctx.channel.send(embed=preview_embed)
                    try:
                        mon_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        mon_msg = None
                    await utils.safe_delete(mon_wait)
                    if not mon_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(mon_msg)
                    if mon_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif "y" in mon_msg.clean_content.lower():
                        stats = True
                        break
                    elif "n" in mon_msg.clean_content.lower():
                        break
        if error:
            preview_embed.clear_fields()
            preview_embed.add_field(name=_('**Pokedex Cancelled**'), value=_("Meowth! Your search has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await ctx.channel.send(embed=preview_embed, delete_after=10)
            return
        preview_embed.clear_fields()
        pokemon.size = None
        key_list = []
        forms = [x.title() for x in ctx.bot.pkmn_info[pokemon.name.lower()]['forms'].keys()]
        if not forms:
            forms = ["None"]
        form_list = []
        for form in forms:
            form_str = ""
            form_key = ""
            if self.bot.pkmn_info[pokemon.name.lower()]['forms'][str(form).lower()].get('shiny', False):
                if "S = Shiny Available" not in key_list:
                    key_list.append("S = Shiny Available")
                form_key += "S"
            if self.bot.pkmn_info[pokemon.name.lower()]['forms'][str(form).lower()].get('gender', False):
                if "G = Gender Differences" not in key_list:
                    key_list.append("G = Gender Differences")
                form_key += "G"
            if self.bot.pkmn_info[pokemon.name.lower()]['forms'][str(form).lower()].get('shadow', False):
                if "R = Team Rocket Shadow" not in key_list:
                    key_list.append("R = Team Rocket Shadow")
                form_key += "R"
            if "S" in form_key or "G" in form_key or "R" in form_key:
                form_key = f"**({form_key})**"
            if form == "None" and "Normal" in forms:
                continue
            elif form == "None":
                form = "Normal"
            form_str = f"{form} {form_key}"
            form_list.append(form_str.strip())
        preview_embed.add_field(name=f"{str(pokemon)} - #{pokemon.id} - {pokemon.emoji} - {('').join(pokemon.boost_weather)}{' - *Legendary*' if pokemon.legendary else ''}{' - *Mythical*' if pokemon.mythical else ''}", value=pokemon.pokedex, inline=False)
        if len(forms) > 1 or key_list:
            preview_embed.add_field(name=f"{pokemon.name.title()} Forms:", value=", ".join(form_list), inline=True)
        if len(pokemon.evolution.split("→")) > 1:
            preview_embed.add_field(name=f"{pokemon.name.title()} Evolution:", value=pokemon.evolution.replace(pokemon.name.title(), f"**{pokemon.name.title()}**"), inline=False)
        if all([pokemon.base_stamina, pokemon.base_attack, pokemon.base_defense]):
            preview_embed.add_field(name=f"{pokemon.name.title()} CP by Level (Raids / Research):", value=f"15: **{pokemon.research_cp}** | 20: **{pokemon.raid_cp}** | 25: **{pokemon.boost_raid_cp}** | 40: **{pokemon.max_cp}**", inline=False)
        if "stats" in ctx.invoked_with or stats:
            charge_moves = []
            quick_moves = []
            field_value = ""
            if all([pokemon.base_stamina, pokemon.base_attack, pokemon.base_defense]):
                field_value += f"Base Stats: Attack: **{pokemon.base_attack}** | Defense: **{pokemon.base_defense}** | Stamina: **{pokemon.base_stamina}**\n"
            if pokemon.height and pokemon.weight:
                field_value += f"Height: **{round(pokemon.height, 3)}m** | Weight: **{round(pokemon.weight, 3)}kg**\n"
            if pokemon.evolves:
                field_value += f"Evolution Candy: **{pokemon.evolve_candy}**\n"
            if pokemon.buddy_distance:
                field_value += f"Buddy Distance: **{pokemon.buddy_distance}km**\n"
            if pokemon.charge_moves:
                charge_moves = [f"{x.title()} {utils.type_to_emoji(self.bot, utils.get_move_type(self.bot, x))}" for x in pokemon.charge_moves]
            if pokemon.quick_moves:
                quick_moves = [f"{x.title()} {utils.type_to_emoji(self.bot, utils.get_move_type(self.bot, x))}" for x in pokemon.quick_moves]
            if charge_moves or quick_moves:
                field_value += f"{'Quick Moves: **'+(', ').join(quick_moves)+'**' if quick_moves else ''}\n{'Charge Moves: **'+(', ').join(charge_moves)+'**' if charge_moves else ''}"
            if field_value:
                preview_embed.add_field(name="Other Info:", value=field_value, inline=False)
        preview_embed.set_thumbnail(url=pokemon.img_url)
        if key_list:
            preview_embed.set_footer(text=(' | ').join(key_list))
        pokedex_msg = await ctx.send(embed=preview_embed)

    @pokedex.command()
    async def stats(self, ctx, *, pokemon: str=None):
        """Detailed Pokedex information for a pokemon

        Usage: !pokedex stats <pokemon with form, gender, etc>"""
        await ctx.invoke(self.bot.get_command('pokedex'), pokemon=pokemon)


def setup(bot):
    bot.add_cog(Pokedex(bot))

def teardown(bot):
    bot.remove_cog(Pokedex)
