from pathlib import Path
from django.utils.text import slugify
import pandas as pd
import math
from proteins.models import Dye
from django.db import transaction
import numpy as np

DATA_DIR = Path(__file__).parent.parent / "data"
BIOTIUM_DYES = DATA_DIR / "Biotium-121823-dye-list.csv"
BIOTIUM_DATA = DATA_DIR / "Biotium-121823-data.csv"


existing = {d.name: d for d in Dye.objects.filter(manufacturer="Biotium")}

# names that need to be changed to match the names in the data file
# map of new name to old name
NAME_CHANGES = {
    "MemBrite Fix 660/680": "MemBrite Fix 660",
    "MemBrite Fix 680/700": "MemBrite Fix 680",
    "MemBrite Fix 543/560": "MemBrite Fix 543",
    "MemBrite Fix 640/660": "MemBrite Fix 640",
    "MemBrite Fix 594/615": "MemBrite Fix 594",
    "MemBrite Fix 488/515": "MemBrite Fix 488",
    "MemBrite Fix 568/580": "MemBrite Fix 568",
    "MemBrite Fix 405/430": "MemBrite Fix 405",
    "BactoView Live Red": "BactoView Red",
    "BactoView Live Green": "BactoView Green",
    "PE (R-PE / R-phycoerythrin)": "PE (R-PE, R-phycoerythrin)",
}
SKIP_NAMES = {"RFP", "YFP", "mCherry", "CFP", "EGFP", "EGFP (GFP)", "Hoechst"}

# these are the names of dyes that have been attributed to Biotium
# but which are not in the Biotium data file
# 'Tetramethylrhodamine (TAMRA, TRITC)',
# 'RPE-CF647T',
# 'Hoechst 34580'


@transaction.atomic
def add_biotium_data():
    """Add Biotium dyes to the database."""

    dyes = pd.read_csv(BIOTIUM_DYES)
    data = pd.read_csv(BIOTIUM_DATA)
    processed = set()
    # note all the dye names have a space at the end

    for _, (name, manufacturer, *__) in dyes.iterrows():
        name = name.strip()
        if isinstance(manufacturer, float) and math.isnan(manufacturer):
            manufacturer = ""
        if name in SKIP_NAMES:
            print(f"❌ Skipping {name}")
            continue
        processed.add(name)
        slug = slugify(name.replace("/", "-"))

        # get the dye instance
        if (
            name in NAME_CHANGES
            and Dye.objects.filter(name=NAME_CHANGES[name]).exists()
        ):
            # check for existing dyes that need name changes
            dye = Dye.objects.get(name=NAME_CHANGES[name])
            dye.name = name
            dye.slug = slug
            print(f"🆙 Updated {NAME_CHANGES[name]}->{name}")
        else:
            # otherwise look for a dye with the same slug
            try:
                dye = Dye.objects.get(slug=slug)
                print(f"👀 Found {name}")
            except Dye.DoesNotExist:
                if manufacturer != "Biotium":
                    print(f"❌ Skipping {name}")
                    continue
                dye = Dye(name=name, slug=slug)
                print(f"✨ Created {name} ({manufacturer})")

        # update manufacturer ... in case it was misattributed to Biotium
        dye.manufacturer = manufacturer
        if not manufacturer:
            dye.url = ""
        dye.save()

        abs_data = np.asarray(data[["Wavelength(nm)", name + " Abs"]].dropna()).tolist()
        dye.spectra.update_or_create(
            owner_dye=dye, subtype="ab", category="d", defaults={"data": abs_data}
        )

        em_data = np.asarray(data[["Wavelength(nm)", name + " Em"]].dropna()).tolist()
        dye.spectra.update_or_create(
            owner_dye=dye, subtype="em", category="d", defaults={"data": em_data}
        )

    # check existing dyes that aren't in the data file
    for name, dye in existing.items():
        if name not in processed.union(NAME_CHANGES.values()):
            print(f"🔗 Disowning {dye}")
            dye.manufacturer = ""
            dye.url = ""
            # dye.save()
