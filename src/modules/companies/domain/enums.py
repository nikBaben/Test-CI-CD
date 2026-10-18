"""Enums для бизнес сущности 'компания'."""
from enum import StrEnum


class SalesModel(StrEnum):
    """Модель продаж по типу клиента."""
    B2B = "B2B"
    B2C = "B2C"
    B2G = "B2G"


class PrimarySalesChannel(StrEnum):
    """Основной канал продаж."""
    MARKETPLACE = "marketplace"


class Seasonality(StrEnum):
    """Сезонность бизнеса."""
    STEADY_YEAR = "Steady_Year"
    SUMMER_SPRING_PEAK = "Summer/Spring_Peak"
    WINTER_AUTUMN_PEAK = "Winter/Autumn_Peak"


class TaxRegime(StrEnum):
    """Форма налогооблажения."""
    OSNO = "OSNO"
    USN = "USN"
    ESXH = "ESXH"
    PSN = "PSN"
    NPD = "NPD"
    AUSN = "AUSN"


class KeyVulnerability(StrEnum):
    """Основной фактор риска."""
    IMPORT_EXCHANGE_RATE = "Import_Exchange_Rate"
    HIGH_RELIANCE_LOANS_LEASING = "High_Reliance_Loans_Leasing"


class CEOGoal(StrEnum):
    """Цель комапнии на год."""
    AGGRESIVE_GROWTH_SCALING = "Aggressive_Growth_Scaling"
    MAINTAINING_MARKET_POSITION_COST_OPTIMIZATION = "Maintaining_Market_Position_Cost_Optimization"
    ACHIEVING_PROFITABILITY_RESOLVING_CASH_FLOW_ISSUES = "Achieving_Profitability_Resolving_Cash_Flow_Issues"


class EconomicsSectors(StrEnum):
    """"Экономический сектор компании."""
    A = "Сельское, лесное хозяйство, охота, рыболовство и рыбоводство"
    B = "Добыча полезных ископаемых"
    C = "Обрабатывающие производства"
    D = "Электроэнергия, газ, пар и кондиционирование воздуха"
    E = "Водоснабжение, водоотведение и обращение с отходами"
    F = "Строительство"
    G = "Оптовая и розничная торговля; ремонт автотранспортных средств"
    H = "Транспортировка и хранение"
    I = "Деятельность гостиниц и предприятий общественного питания"
    J = "Деятельность в области информации и связи"
    K = "Финансовая и страховая деятельность"
    L = "Операции с недвижимым имуществом"
    M = "Профессиональная, научная и техническая деятельность"
    N = "Административная деятельность и сопутствующие услуги"
    O = "Государственное управление, обеспечение военной безопасности и социальное обеспечение"
    P = "Образование"
    Q = "Здравоохранение и социальные услуги"
    R = "Культура, спорт, досуг и развлечения"
    S = "Предоставление прочих видов услуг"
    T = "Деятельность домашних хозяйств"
    U = "Деятельность экстерриториальных организаций и органов"


SECTORS = (
    (1, 3, EconomicsSectors.A),
    (5, 9, EconomicsSectors.B),
    (10, 33, EconomicsSectors.C),
    (35, 35, EconomicsSectors.D),
    (36, 39, EconomicsSectors.E),
    (41, 43, EconomicsSectors.F),
    (45, 47, EconomicsSectors.G),
    (49, 53, EconomicsSectors.H),
    (55, 56, EconomicsSectors.I),
    (58, 63, EconomicsSectors.J),
    (64, 66, EconomicsSectors.K),
    (68, 68, EconomicsSectors.L),
    (69, 75, EconomicsSectors.M),
    (77, 82, EconomicsSectors.N),
    (84, 84, EconomicsSectors.O),
    (85, 85, EconomicsSectors.P),
    (86, 88, EconomicsSectors.Q),
    (90, 93, EconomicsSectors.R),
    (94, 96, EconomicsSectors.S),
    (97, 98, EconomicsSectors.T),
    (99, 99, EconomicsSectors.U)
)

