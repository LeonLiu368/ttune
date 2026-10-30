"""Made-up names for the paperwork: surnames, employers, landlords, providers. None is a real business."""

SURNAMES = (
    "Garcia", "Johnson", "Nguyen", "Okafor", "Patel", "Rivera", "Chen", "Williams", "Haddad", "Kowalski",
    "Mensah", "Lopez", "Brown", "Tran", "Ramirez", "Davis", "Kim", "Abdi", "Martinez", "Jackson", "Singh", "Moore",
    "Hernandez", "Thompson", "Ali", "Reyes", "Walker", "Castillo", "Young", "Adeyemi", "Morales", "Clark",
    "Petrov", "Flores", "Lewis", "Vargas", "Hall", "Mendoza", "Allen", "Nakamura", "Ortiz", "Wright",
)

EMPLOYERS = (
    "Northgate Logistics LLC", "Riverside Grocery Co-op", "Summit Home Health Services", "Bright Smile Dental Group",
    "Cedar Valley School District", "Harbor View Nursing Center", "Metro Transit Cleaning Inc.",
    "Greenfield Distribution Center", "Lakeside Family Restaurant", "Pinecrest Hotel & Suites",
    "Keystone Auto Parts", "Sunrise Child Development Center", "Bluebird Call Center Solutions",
    "Copper Kettle Bakery", "Westside Hardware Supply", "Evergreen Landscaping Co.", "Union Street Pharmacy",
    "Prairie Packaging Corp.", "Maple Leaf Assisted Living", "Silver Line Security Services",
)

PLATFORMS = ("RideLink", "DashCart", "TaskHive", "CleanCrew", "ShopRunner Flex")

LANDLORDS = (
    "Oakmont Property Management", "J. & R. Rentals LLC", "Fairway Apartments", "Hillside Realty Group",
    "Brookstone Residential", "Parkview Housing LLC", "Redwood Court Apartments", "Main Street Properties",
)

CHILDCARE = (
    "Little Acorns Learning Center", "Kids First Child Care", "Rainbow Bridge Preschool", "Happy Hearts Daycare",
    "Tiny Steps Early Learning",
)

PHARMACIES = ("Corner Drug & Wellness", "Valley Community Pharmacy", "Fifth Street Pharmacy", "CareWay Pharmacy")

UTILITIES = ("Tri-County Gas & Electric", "Consolidated Energy Services", "Hometown Power & Light")

COLLEGES = ("Lakeshore Community College", "State Technical College", "Riverbend University", "Midland State College")

CLINICS = ("Community Health Partners Clinic", "Westview Women's Health", "Family Care Medical Group")

TOWNS = ("Fairview", "Riverside", "Greenville", "Madison", "Clinton", "Franklin", "Georgetown", "Springdale",
         "Oak Grove", "Centerville", "Bristol", "Milford")

STREETS = ("Cedar Street", "Maple Avenue", "Oak Lane", "Washington Street", "Park Road", "Lincoln Avenue",
           "Elm Court", "Hillcrest Drive", "River Road", "Church Street", "Pine Street", "Sunset Boulevard")

# Short forms a document might use instead of the name on the application.
NICKNAMES = {
    "Samuel": "Sam", "Daniel": "Dan", "David": "Dave", "Abigail": "Abby", "Isabel": "Izzy", "Andres": "Andy",
    "Ricardo": "Rick", "Olivia": "Liv", "Mohammed": "Mo", "Elena": "Ellie", "Tomas": "Tom", "Victor": "Vic",
    "Jasmine": "Jas", "Esperanza": "Espe", "Destiny": "Des", "Hannah": "Annie", "Marcus": "Marc", "Naomi": "Nomi",
}

# States with no tax on wages: their pay stubs have no state withholding line.
NO_WAGE_TAX = frozenset({"AK", "FL", "NV", "NH", "SD", "TN", "TX", "WA", "WY"})
