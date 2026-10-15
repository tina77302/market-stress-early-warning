# Standard experience for every registered user

Market Stress Early Warning is a portfolio/demo application. The previously
planned Pro experience is the standard experience for every registered user.
There are no Free/Pro product tiers, upgrade prompts, paywalls, Pro-only badges,
or plan-based feature gates.

Investment, Paper Trading, Portfolio Risk, Sector/Industry Stress, Stress
Sensitivity, 10D Portfolio Outlook, and the future AI Risk Advisor must use the
same functionality and data quality for every registered user. An unfinished
feature may be unavailable to everyone until implemented; it must not be locked
behind a plan or role.

The admin role grants administrative privileges only. It must not affect
starting capital, security universe, market-data quality, FX, fees, trading
rules, orders, portfolio calculations, or analytics quality. This applies
equally to admin1, user1, and future registrations.

If a legacy plan field exists, it may remain for compatibility but must be
ignored when authorizing or calculating product features. Do not introduce a
database migration solely to remove it.

Market-stress monitoring remains the primary product; portfolio and currency
analytics explain recorded exposure and outcomes alongside validated signals.
