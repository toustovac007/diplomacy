from django.core.management.base import BaseCommand

from apps.maps.models import Country, Province, Coast, ProvinceAdjacency


COUNTRIES = [
    ("AUS", "Rakousko-Uhersko"),
    ("ENG", "Anglie"),
    ("FRA", "Francie"),
    ("GER", "Německo"),
    ("ITA", "Itálie"),
    ("RUS", "Rusko"),
    ("TUR", "Turecko"),
]

# code, name, province_type, is_supply_center, home_country_code
PROVINCES = [
    # Austria
    ("BOH", "Bohemia", "inland", False, None),
    ("BUD", "Budapest", "inland", True, "AUS"),
    ("GAL", "Galicia", "inland", False, None),
    ("TRI", "Trieste", "coastal", True, "AUS"),
    ("TYR", "Tyrolia", "inland", False, None),
    ("VIE", "Vienna", "inland", True, "AUS"),

    # England
    ("CLY", "Clyde", "coastal", False, None),
    ("EDI", "Edinburgh", "coastal", True, "ENG"),
    ("LVP", "Liverpool", "coastal", True, "ENG"),
    ("LON", "London", "coastal", True, "ENG"),
    ("WAL", "Wales", "coastal", False, None),
    ("YOR", "Yorkshire", "coastal", False, None),

    # France
    ("BRE", "Brest", "coastal", True, "FRA"),
    ("BUR", "Burgundy", "inland", False, None),
    ("GAS", "Gascony", "coastal", False, None),
    ("MAR", "Marseilles", "coastal", True, "FRA"),
    ("PAR", "Paris", "inland", True, "FRA"),
    ("PIC", "Picardy", "coastal", False, None),

    # Germany
    ("BER", "Berlin", "coastal", True, "GER"),
    ("KIE", "Kiel", "coastal", True, "GER"),
    ("MUN", "Munich", "inland", True, "GER"),
    ("PRU", "Prussia", "coastal", False, None),
    ("RUH", "Ruhr", "inland", False, None),
    ("SIL", "Silesia", "inland", False, None),

    # Italy
    ("APU", "Apulia", "coastal", False, None),
    ("NAP", "Naples", "coastal", True, "ITA"),
    ("PIE", "Piedmont", "coastal", False, None),
    ("ROM", "Rome", "coastal", True, "ITA"),
    ("TUS", "Tuscany", "coastal", False, None),
    ("VEN", "Venice", "coastal", True, "ITA"),

    # Russia
    ("FIN", "Finland", "coastal", False, None),
    ("LVN", "Livonia", "coastal", False, None),
    ("MOS", "Moscow", "inland", True, "RUS"),
    ("SEV", "Sevastopol", "coastal", True, "RUS"),
    ("STP", "St. Petersburg", "coastal", True, "RUS"),
    ("UKR", "Ukraine", "inland", False, None),
    ("WAR", "Warsaw", "inland", True, "RUS"),

    # Turkey
    ("ANK", "Ankara", "coastal", True, "TUR"),
    ("ARM", "Armenia", "coastal", False, None),
    ("CON", "Constantinople", "coastal", True, "TUR"),
    ("SMY", "Smyrna", "coastal", True, "TUR"),
    ("SYR", "Syria", "coastal", False, None),

    # Neutral land provinces
    ("ALB", "Albania", "coastal", False, None),
    ("BEL", "Belgium", "coastal", True, None),
    ("BUL", "Bulgaria", "coastal", True, None),
    ("DEN", "Denmark", "coastal", True, None),
    ("GRE", "Greece", "coastal", True, None),
    ("HOL", "Holland", "coastal", True, None),
    ("NWY", "Norway", "coastal", True, None),
    ("NAF", "North Africa", "coastal", False, None),
    ("POR", "Portugal", "coastal", True, None),
    ("RUM", "Rumania", "coastal", True, None),
    ("SER", "Serbia", "inland", True, None),
    ("SPA", "Spain", "coastal", True, None),
    ("SWE", "Sweden", "coastal", True, None),
    ("TUN", "Tunis", "coastal", True, None),

    # Water
    ("ADR", "Adriatic Sea", "sea", False, None),
    ("AEG", "Aegean Sea", "sea", False, None),
    ("BAL", "Baltic Sea", "sea", False, None),
    ("BAR", "Barents Sea", "sea", False, None),
    ("BLA", "Black Sea", "sea", False, None),
    ("EAS", "Eastern Mediterranean", "sea", False, None),
    ("ENG", "English Channel", "sea", False, None),
    ("BOT", "Gulf of Bothnia", "sea", False, None),
    ("LYO", "Gulf of Lyon", "sea", False, None),
    ("HEL", "Helgoland Bight", "sea", False, None),
    ("ION", "Ionian Sea", "sea", False, None),
    ("IRI", "Irish Sea", "sea", False, None),
    ("MAO", "Mid-Atlantic Ocean", "sea", False, None),
    ("NAO", "North Atlantic Ocean", "sea", False, None),
    ("NTH", "North Sea", "sea", False, None),
    ("NWG", "Norwegian Sea", "sea", False, None),
    ("SKA", "Skagerrak", "sea", False, None),
    ("TYS", "Tyrrhenian Sea", "sea", False, None),
    ("WES", "Western Mediterranean", "sea", False, None),
]

# Only the three standard multi-coast provinces need explicit Coast rows.
COASTS = [
    ("BUL", "ec"),
    ("BUL", "sc"),
    ("SPA", "nc"),
    ("SPA", "sc"),
    ("STP", "nc"),
    ("STP", "sc"),
]

# Undirected movement edges. Location syntax can be PROVINCE or PROVINCE/coast.
# Units: "A" = army, "F" = fleet, "AF" = both.
# These are the standard Diplomacy movement adjacencies.
EDGES = [
    # Austria
    ("BOH", "MUN", "A"),
    ("BOH", "SIL", "A"),
    ("BOH", "GAL", "A"),
    ("BOH", "VIE", "A"),
    ("BOH", "TYR", "A"),
    ("BUD", "VIE", "A"),
    ("BUD", "GAL", "A"),
    ("BUD", "RUM", "A"),
    ("BUD", "SER", "A"),
    ("BUD", "TRI", "A"),
    ("GAL", "WAR", "A"),
    ("GAL", "UKR", "A"),
    ("GAL", "RUM", "A"),
    ("GAL", "VIE", "A"),
    ("TRI", "TYR", "A"),
    ("TRI", "VIE", "A"),
    ("TRI", "SER", "A"),
    ("TRI", "ALB", "AF"),
    ("TRI", "ADR", "F"),
    ("TRI", "VEN", "AF"),
    ("TYR", "MUN", "A"),
    ("TYR", "VIE", "A"),
    ("TYR", "VEN", "A"),
    ("TYR", "PIE", "A"),

    # England
    ("CLY", "NAO", "F"),
    ("CLY", "NWG", "F"),
    ("CLY", "EDI", "AF"),
    ("CLY", "LVP", "AF"),
    ("EDI", "NWG", "F"),
    ("EDI", "NTH", "F"),
    ("EDI", "YOR", "AF"),
    ("EDI", "LVP", "A"),
    ("LVP", "IRI", "F"),
    ("LVP", "YOR", "A"),
    ("LVP", "WAL", "AF"),
    ("LVP", "NAO", "F"),
    ("LON", "WAL", "AF"),
    ("LON", "YOR", "AF"),
    ("LON", "NTH", "F"),
    ("LON", "ENG", "F"),
    ("WAL", "IRI", "F"),
    ("WAL", "YOR", "A"),
    ("WAL", "ENG", "F"),
    ("YOR", "NTH", "F"),

    # France
    ("BRE", "ENG", "F"),
    ("BRE", "PIC", "AF"),
    ("BRE", "PAR", "A"),
    ("BRE", "GAS", "AF"),
    ("BRE", "MAO", "F"),
    ("BUR", "PAR", "A"),
    ("BUR", "PIC", "A"),
    ("BUR", "BEL", "A"),
    ("BUR", "RUH", "A"),
    ("BUR", "MUN", "A"),
    ("BUR", "MAR", "A"),
    ("BUR", "GAS", "A"),
    ("GAS", "MAO", "F"),
    ("GAS", "PAR", "A"),
    ("GAS", "MAR", "A"),
    ("GAS", "SPA", "A"),
    ("GAS", "SPA/nc", "F"),
    ("MAR", "SPA", "A"),
    ("MAR", "SPA/sc", "F"),
    ("MAR", "LYO", "F"),
    ("MAR", "PIE", "AF"),
    ("PAR", "PIC", "A"),
    ("PIC", "ENG", "F"),
    ("PIC", "BEL", "AF"),

    # Germany
    ("BER", "KIE", "AF"),
    ("BER", "BAL", "F"),
    ("BER", "PRU", "AF"),
    ("BER", "SIL", "A"),
    ("BER", "MUN", "A"),
    ("KIE", "HEL", "F"),
    ("KIE", "DEN", "AF"),
    ("KIE", "MUN", "A"),
    ("KIE", "RUH", "A"),
    ("KIE", "HOL", "AF"),
    ("MUN", "RUH", "A"),
    ("MUN", "SIL", "A"),
    ("PRU", "BAL", "F"),
    ("PRU", "LVN", "AF"),
    ("PRU", "WAR", "A"),
    ("PRU", "SIL", "A"),
    ("RUH", "BEL", "A"),
    ("RUH", "HOL", "A"),
    ("SIL", "WAR", "A"),

    # Italy
    ("APU", "VEN", "AF"),
    ("APU", "ADR", "F"),
    ("APU", "ION", "F"),
    ("APU", "NAP", "AF"),
    ("APU", "ROM", "A"),
    ("NAP", "ROM", "AF"),
    ("NAP", "ION", "F"),
    ("NAP", "TYS", "F"),
    ("PIE", "VEN", "A"),
    ("PIE", "TUS", "AF"),
    ("PIE", "LYO", "F"),
    ("ROM", "TUS", "AF"),
    ("ROM", "VEN", "A"),
    ("ROM", "TYS", "F"),
    ("TUS", "LYO", "F"),
    ("TUS", "VEN", "A"),
    ("TUS", "TYS", "F"),
    ("VEN", "ADR", "F"),

    # Russia
    ("FIN", "NWY", "A"),
    ("FIN", "SWE", "AF"),
    ("FIN", "BOT", "F"),
    ("FIN", "STP", "A"),
    ("FIN", "STP/sc", "F"),
    ("LVN", "BOT", "F"),
    ("LVN", "STP", "A"),
    ("LVN", "STP/sc", "F"),
    ("LVN", "MOS", "A"),
    ("LVN", "WAR", "A"),
    ("LVN", "BAL", "F"),
    ("MOS", "STP", "A"),
    ("MOS", "SEV", "A"),
    ("MOS", "UKR", "A"),
    ("MOS", "WAR", "A"),
    ("SEV", "UKR", "A"),
    ("SEV", "ARM", "AF"),
    ("SEV", "BLA", "F"),
    ("SEV", "RUM", "AF"),
    ("STP", "NWY", "A"),
    ("STP/nc", "NWY", "F"),
    ("STP/nc", "BAR", "F"),
    ("STP/sc", "BOT", "F"),
    ("UKR", "WAR", "A"),
    ("UKR", "RUM", "A"),

    # Turkey
    ("ANK", "BLA", "F"),
    ("ANK", "ARM", "AF"),
    ("ANK", "SMY", "A"),
    ("ANK", "CON", "AF"),
    ("ARM", "BLA", "F"),
    ("ARM", "SYR", "A"),
    ("ARM", "SMY", "A"),
    ("CON", "BUL", "A"),
    ("CON", "BUL/ec", "F"),
    ("CON", "BUL/sc", "F"),
    ("CON", "BLA", "F"),
    ("CON", "SMY", "AF"),
    ("CON", "AEG", "F"),
    ("SMY", "SYR", "AF"),
    ("SMY", "EAS", "F"),
    ("SMY", "AEG", "F"),
    ("SYR", "EAS", "F"),

    # Neutral land provinces
    ("ALB", "SER", "A"),
    ("ALB", "GRE", "AF"),
    ("ALB", "ION", "F"),
    ("BEL", "ENG", "F"),
    ("BEL", "NTH", "F"),
    ("BEL", "HOL", "AF"),
    ("BUL", "SER", "A"),
    ("BUL", "RUM", "A"),
    ("BUL", "GRE", "A"),
    ("BUL/ec", "RUM", "F"),
    ("BUL/ec", "BLA", "F"),
    ("BUL/sc", "GRE", "F"),
    ("BUL/sc", "AEG", "F"),
    ("DEN", "NTH", "F"),
    ("DEN", "SKA", "F"),
    ("DEN", "BAL", "F"),
    ("DEN", "HEL", "F"),
    ("GRE", "SER", "A"),
    ("GRE", "AEG", "F"),
    ("GRE", "ION", "F"),
    ("HOL", "NTH", "F"),
    ("HOL", "HEL", "F"),
    ("NWY", "NWG", "F"),
    ("NWY", "BAR", "F"),
    ("NWY", "SWE", "AF"),
    ("NWY", "SKA", "F"),
    ("NWY", "NTH", "F"),
    ("POR", "MAO", "F"),
    ("POR", "SPA", "A"),
    ("POR", "SPA/nc", "F"),
    ("POR", "SPA/sc", "F"),
    ("RUM", "SER", "A"),
    ("RUM", "BLA", "F"),
    ("SPA/nc", "MAO", "F"),
    ("SPA/sc", "MAO", "F"),
    ("SPA/sc", "LYO", "F"),
    ("SPA/sc", "WES", "F"),
    ("SWE", "SKA", "F"),
    ("SWE", "BAL", "F"),
    ("SWE", "BOT", "F"),
    ("SWE", "DEN", "AF"),
    ("TUN", "WES", "F"),
    ("TUN", "TYS", "F"),
    ("TUN", "ION", "F"),
    ("TUN", "NAF", "AF"),
    ("NAF", "WES", "F"),
    ("NAF", "MAO", "F"),

    # Sea-to-sea
    ("ADR", "ION", "F"),
    ("AEG", "EAS", "F"),
    ("AEG", "ION", "F"),
    ("BAL", "BOT", "F"),
    ("BAR", "NWG", "F"),
    ("EAS", "ION", "F"),
    ("ENG", "IRI", "F"),
    ("ENG", "NTH", "F"),
    ("ENG", "MAO", "F"),
    ("LYO", "TYS", "F"),
    ("LYO", "WES", "F"),
    ("HEL", "NTH", "F"),
    ("ION", "TYS", "F"),
    ("IRI", "NAO", "F"),
    ("IRI", "MAO", "F"),
    ("MAO", "WES", "F"),
    ("MAO", "NAO", "F"),
    ("NAO", "NWG", "F"),
    ("NTH", "NWG", "F"),
    ("TYS", "WES", "F"),
]


class Command(BaseCommand):
    help = "Naplní databázi kompletní standardní mapou Diplomacy."

    def handle(self, *args, **options):
        self._seed_countries()
        self._seed_provinces()
        self._seed_coasts()
        self._seed_adjacencies()
        self._validate_map()

        self.stdout.write(
            self.style.SUCCESS("Kompletní standardní mapa Diplomacy byla vytvořena a ověřena.")
        )

    def _seed_countries(self):
        for code, name in COUNTRIES:
            Country.objects.update_or_create(code=code, defaults={"name": name})

        self.stdout.write(f"Státy: {Country.objects.filter(code__in=[c[0] for c in COUNTRIES]).count()}")

    def _seed_provinces(self):
        countries = {country.code: country for country in Country.objects.all()}

        for code, name, province_type, is_supply_center, home_country_code in PROVINCES:
            Province.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "province_type": province_type,
                    "is_supply_center": is_supply_center,
                    "home_country": countries.get(home_country_code),
                },
            )

        self.stdout.write(f"Provincie: {Province.objects.filter(code__in=[p[0] for p in PROVINCES]).count()}")

    def _seed_coasts(self):
        for province_code, coast_code in COASTS:
            province = Province.objects.get(code=province_code)
            Coast.objects.update_or_create(
                province=province,
                code=coast_code,
            )

        self.stdout.write(f"Pobřeží: {Coast.objects.filter(province__code__in=['BUL', 'SPA', 'STP']).count()}")

    @staticmethod
    def _location(location):
        if "/" in location:
            province_code, coast_code = location.split("/", 1)
        else:
            province_code, coast_code = location, None

        province = Province.objects.get(code=province_code)
        coast = None

        if coast_code:
            coast = Coast.objects.get(
                province=province,
                code=coast_code,
            )

        return province, coast

    def _seed_adjacencies(self):
        # Map adjacency is static metadata. Rebuilding it prevents old/test edges
        # from remaining in the database after changes to the seed data.
        ProvinceAdjacency.objects.all().delete()

        for location_a, location_b, units in EDGES:
            province_a, coast_a = self._location(location_a)
            province_b, coast_b = self._location(location_b)

            army_allowed = "A" in units
            fleet_allowed = "F" in units

            ProvinceAdjacency.objects.create(
                from_province=province_a,
                to_province=province_b,
                from_coast=coast_a,
                to_coast=coast_b,
                army_allowed=army_allowed,
                fleet_allowed=fleet_allowed,
            )

            ProvinceAdjacency.objects.create(
                from_province=province_b,
                to_province=province_a,
                from_coast=coast_b,
                to_coast=coast_a,
                army_allowed=army_allowed,
                fleet_allowed=fleet_allowed,
            )

        self.stdout.write(
            f"Směrové sousednosti: {ProvinceAdjacency.objects.count()} "
            f"({len(EDGES)} obousměrných hran)"
        )

    def _validate_map(self):
        expected_codes = {province[0] for province in PROVINCES}
        actual_codes = set(
            Province.objects.filter(code__in=expected_codes).values_list("code", flat=True)
        )

        if actual_codes != expected_codes:
            missing = sorted(expected_codes - actual_codes)
            raise RuntimeError(f"Chybí provincie: {missing}")

        if len(PROVINCES) != 75:
            raise RuntimeError(f"Definice mapy má {len(PROVINCES)} provincií místo 75.")

        supply_centers = Province.objects.filter(
            code__in=expected_codes,
            is_supply_center=True,
        ).count()
        if supply_centers != 34:
            raise RuntimeError(f"Mapa má {supply_centers} supply center místo 34.")

        home_centers = Province.objects.filter(
            code__in=expected_codes,
            is_supply_center=True,
            home_country__isnull=False,
        ).count()
        if home_centers != 22:
            raise RuntimeError(f"Mapa má {home_centers} domácích center místo 22.")

        coast_set = set(
            Coast.objects.filter(province__code__in=["BUL", "SPA", "STP"])
            .values_list("province__code", "code")
        )
        if coast_set != set(COASTS):
            raise RuntimeError(f"Chybná pobřeží: {sorted(coast_set)}")

        # Every generated route must exist in both directions with identical unit permissions.
        for adjacency in ProvinceAdjacency.objects.select_related(
            "from_province", "to_province", "from_coast", "to_coast"
        ):
            reverse_exists = ProvinceAdjacency.objects.filter(
                from_province=adjacency.to_province,
                to_province=adjacency.from_province,
                from_coast=adjacency.to_coast,
                to_coast=adjacency.from_coast,
                army_allowed=adjacency.army_allowed,
                fleet_allowed=adjacency.fleet_allowed,
            ).exists()

            if not reverse_exists:
                raise RuntimeError(f"Chybí opačná sousednost pro {adjacency}.")

        # Important standard-map non-adjacencies: fleets must go through a province/canal.
        forbidden_fleet_pairs = [
            ("BLA", "AEG"),  # via Constantinople
            ("BAL", "SKA"),  # via Denmark or Sweden
        ]
        for code_a, code_b in forbidden_fleet_pairs:
            if ProvinceAdjacency.objects.filter(
                from_province__code=code_a,
                to_province__code=code_b,
                fleet_allowed=True,
            ).exists():
                raise RuntimeError(f"Neplatná fleet sousednost {code_a} -> {code_b}.")

        # Inland provinces must never have a fleet route.
        invalid_inland_fleet = ProvinceAdjacency.objects.filter(
            fleet_allowed=True,
            from_province__province_type="inland",
        ).exists()
        if invalid_inland_fleet:
            raise RuntimeError("Vnitrozemská provincie má povolený pohyb flotily.")

        self.stdout.write(
            self.style.SUCCESS(
                "Kontrola: 75 provincií, 34 center, 22 domácích center, "
                "6 pobřeží a obousměrné sousednosti jsou v pořádku."
            )
        )
