"""Shared vocabulary: countries, clients, teams, topics, intents.
Rule based on purpose: the planner must be explainable in the demo."""

COUNTRIES = {
    "BE": ["belgium", "belgian", "flanders", "wallonia", "brussels", "belgië"],
    "NL": ["netherlands", "dutch", "holland", "nederland"],
    "DE": ["germany", "german", "deutschland"],
    "FR": ["france", "french"],
    "UK": ["united kingdom", "uk", "british", "england", "great britain"],
}
COUNTRY_NAMES = {"BE": "Belgium", "NL": "Netherlands", "DE": "Germany", "FR": "France", "UK": "United Kingdom"}

CLIENTS = {
    "Colruyt": "BE", "Delhaize": "BE", "Proximus": "BE",
    "Albert Heijn": "NL", "Philips": "NL",
    "Siemens": "DE", "Carrefour": "FR", "Tesco": "UK",
    "Northstar": "BE", "Northstar Logistics": "BE",
}
# Employees of client accounts (from the HR system); lets "Laura's salary" resolve to client Northstar, Belgium.
CLIENT_EMPLOYEES = {"laura peeters": "Northstar", "laura": "Northstar"}

TEAMS = {
    "Payroll": ["payroll", "salary", "wage", "payslip", "voucher", "13th", "thirteenth", "holiday pay", "garnishment", "bonus", "eblox", "cutoff", "payday", "correction run"],
    "Time & Absence": ["leave", "absence", "vacation", "sick", "sickness", "illness", "time registration", "overtime", "timesheet", "parental"],
    "HR": ["onboarding", "contract", "notice", "dismissal", "termination", "hiring", "mobility budget", "new hire"],
    "Integrations": ["sap", "successfactors", "integration", "interface", "api", "idoc"],
}

TOPICS = {
    "notice_period": ["notice period", "notice periods", "notice", "termination", "dismissal", "opzegtermijn", "resign", "resignation"],
    "sick_leave_guaranteed_salary": ["guaranteed salary", "sick leave", "sickness", "illness", "incapacity", "gewaarborgd loon", "sick"],
    "meal_vouchers": ["meal voucher", "meal vouchers", "maaltijdcheque", "face value", "lunch voucher"],
    "holiday_pay": ["holiday pay", "double holiday pay", "vakantiegeld", "single holiday pay"],
    "vacation_days": ["vacation days", "annual leave", "statutory vacation", "days off", "holiday entitlement", "vacation", "leave entitlement"],
    "payroll_engine_eblox": ["eblox", "payroll engine", "engine"],
    "sap_integration": ["sap", "successfactors", "integration", "interface", "idoc"],
    "onboarding": ["onboarding", "new hire", "first day", "starter"],
    "thirteenth_month": ["13th month", "thirteenth month", "weihnachtsgeld", "year-end bonus", "13e mois"],
    "mobility_budget": ["mobility budget", "company car", "bike allowance"],
    "statutory_sick_pay": ["statutory sick pay", "ssp"],
    "time_registration": ["time registration", "clock in", "timesheet", "overtime"],
    "voucher_provider": ["voucher provider", "provider", "edenred", "sodexo", "pluxee", "monizze", "provider switch"],
    "payroll_cutoff": ["cutoff", "cut-off", "cut off", "payroll change", "payroll changes", "deadline", "payday", "correction run", "correction runs", "late changes", "quick guide"],
    "knowledge_governance": ["who decides", "disagree", "contradict", "official source", "governance", "leading", "faq", "trust", "official procedure"],
    "parental_leave": ["parental leave", "parental-leave", "1/5 parental", "ouderschapsverlof", "contractual salary"],
    "public_parental_allowance": ["public allowance", "parental-leave allowance", "parental leave allowance", "public parental", "government benefit", "allowance", "rva", "onem"],
}
TOPIC_LABELS = {
    "payroll_cutoff": "Payroll change cutoff",
    "knowledge_governance": "Knowledge governance",
    "parental_leave": "Parental leave payroll",
    "public_parental_allowance": "Public parental-leave allowance",
    "notice_period": "Notice periods",
    "sick_leave_guaranteed_salary": "Guaranteed salary (sick leave)",
    "meal_vouchers": "Meal vouchers",
    "holiday_pay": "Holiday pay",
    "vacation_days": "Vacation entitlement",
    "payroll_engine_eblox": "eBlox payroll engine",
    "sap_integration": "SAP integration",
    "onboarding": "Onboarding",
    "thirteenth_month": "13th month",
    "mobility_budget": "Mobility budget",
    "statutory_sick_pay": "Statutory sick pay",
    "time_registration": "Time registration",
    "voucher_provider": "Voucher providers",
}

# Query rewrites the planner adds per topic, to catch documents phrased differently.
REWRITES = {
    "notice_period": ["termination notice length white-collar seniority weeks", "opzegtermijn bediende"],
    "sick_leave_guaranteed_salary": ["guaranteed salary period incapacity for work employer pays", "gewaarborgd loon bediende dagen"],
    "meal_vouchers": ["meal voucher face value employer contribution eBlox parameter", "maaltijdcheques nominale waarde"],
    "holiday_pay": ["double holiday pay calculation module", "vakantiegeld berekening"],
    "vacation_days": ["statutory annual leave entitlement full-time employee", "wettelijke vakantiedagen"],
    "payroll_engine_eblox": ["which payroll engine processes the client", "eBlox configuration"],
    "sap_integration": ["SAP SuccessFactors eBlox interface mapping", "integration flow employee master data"],
    "onboarding": ["new hire onboarding checklist first day", "starter documents"],
    "thirteenth_month": ["year-end bonus thirteenth month pro rata", "Weihnachtsgeld"],
    "mobility_budget": ["mobility budget pillars company car", "federal mobility budget"],
    "statutory_sick_pay": ["SSP weekly rate qualifying days"],
    "time_registration": ["clocking overtime timesheet approval"],
    "voucher_provider": ["meal voucher provider switch client Edenred Pluxee Monizze", "voucher issuer contract change"],
    "payroll_cutoff": ["payroll changes must reach SD Worx working days before payday", "cutoff procedure late changes correction run exceptions"],
    "knowledge_governance": ["official procedure is leading when FAQ contradicts", "conflicting sources owner decides"],
    "parental_leave": ["employer-paid contractual salary basis during 1/5 parental leave percent", "parental leave payroll treatment client configuration"],
    "public_parental_allowance": ["public parental-leave allowance amount government benefit", "who handles benefit allowance questions"],
}

INTENTS = {
    "contact": ["who can i ask", "who do i ask", "who should i ask", "who should i contact", "who to ask", "who is responsible", "who owns", "who can i contact"],
    "procedure": ["how do i", "how to", "how can i", "steps", "change", "configure", "process", "set up", "update the"],
    "decision": ["decide", "decided", "decision", "agreed", "agree", "outcome of the meeting"],
    "status": ["status", "bug", "ticket", "progress", "open issue"],
    "rule": ["what is", "what are", "how many", "how much", "which", "does", "is the", "who is"],
}
INTENT_DOC_TYPES = {
    "contact": ["procedure", "wiki", "policy"],
    "procedure": ["procedure", "checklist", "manual", "wiki"],
    "decision": ["meeting", "email", "chat"],
    "status": ["ticket", "chat", "email"],
    "rule": ["policy", "manual", "wiki", "email"],
}

# Channel authority: how much a document type is trusted by construction.
CHANNEL_WEIGHT = {
    "policy": 1.0, "procedure": 0.95, "manual": 0.9, "checklist": 0.85, "wiki": 0.8,
    "analysis": 0.8, "meeting": 0.75, "ticket": 0.7, "email": 0.55, "chat": 0.5,
}
# Freshness half-life in days per document type.
HALF_LIFE_DAYS = {
    "policy": 720, "procedure": 540, "manual": 540, "checklist": 365, "wiki": 365,
    "analysis": 365, "meeting": 180, "ticket": 120, "email": 120, "chat": 90,
}
# Reputation weights per relationship.
REL_WEIGHT = {
    "owns": 2.0, "authored": 2.0, "edited": 1.5, "answered": 1.2,
    "consulted": 1.0, "attended": 0.4, "assigned": 0.8, "reviewed": 1.0, "listed": 1.5,
}

STOPWORDS = set("""a an the of for in on at to from by with and or is are was were be been do does did how many much
what which who where when why can could should would i we you they it this that these those our their your as into
about after before during under over per get gets give employee employees""".split())
