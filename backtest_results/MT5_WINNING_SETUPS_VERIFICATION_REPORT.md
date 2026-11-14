# TradingGuard MT5 Winning Setups Backtest & Verification Report

**Execution Date**: 2026-11-14 20:28:25
**Terminal**: LiteFinance MT5 Demo (Account 91235314)
**Dataset**: Full 2026 M1/M5 Historical Rates with Broker Tick Microstructure

### Executive Summary Table

| Model              | Asset       |   Orders |   Wins |   Losses |   BE |   Expired | WR_Decisive   | WR_Gross   | Net_R   |   PF | PnL_0.01   | PnL_Norm   | MaxDD_R   | MaxDD_USD   |
|:-------------------|:------------|---------:|-------:|---------:|-----:|----------:|:--------------|:-----------|:--------|-----:|:-----------|:-----------|:----------|:------------|
| MODEL-ISB-PC-01    | NQ          |       11 |      2 |        3 |    3 |         3 | 40.0%         | 18.2%      | +3.92R  | 2.31 | $+9.19     | $+391.90   | 2.00R     | $200.00     |
| MODEL-SMT-CD-03    | NQ          |       15 |      5 |        3 |    3 |         4 | 62.5%         | 33.3%      | +9.17R  | 4.06 | $+9.57     | $+917.40   | 2.00R     | $200.00     |
| MODEL-SE-JSR-02    | XAUUSD_o    |        3 |      1 |        1 |    1 |         0 | 50.0%         | 33.3%      | +1.01R  | 2.01 | $+12.73    | $+99.00    | 1.00R     | $100.00     |
| SETUP-ARCH-015     | XAUUSD_o    |       24 |      5 |       13 |    1 |         5 | 27.8%         | 20.8%      | -0.56R  | 0.96 | $+7.39     | $-59.50    | 7.48R     | $751.90     |
| COMBINED PORTFOLIO | MULTI-ASSET |       53 |     13 |       20 |    8 |        12 | 39.4%         | 24.5%      | +13.54R | 1.68 | $+38.88    | $+1,348.80 | 8.48R     | $851.90     |

### Detailed Trade Log (First 20 Trades)

| ID                                       | Model           | Symbol   | Type       | TriggerTime         |    Entry |       SL |       TP | Status    |   Realized_R |   PnL_Norm_USD |
|:-----------------------------------------|:----------------|:---------|:-----------|:--------------------|---------:|---------:|---------:|:----------|-------------:|---------------:|
| TG-MODEL-ISB-PC-01-NQ-20260804-1410-001  | MODEL-ISB-PC-01 | NQ       | BUY_LIMIT  | 2026.08.04 14:10:00 | 29007.2  | 28983.6  | 29089.8  | WIN       |        3.458 |          345.8 |
| TG-MODEL-SMT-CD-03-NQ-20260805-0925-002  | MODEL-SMT-CD-03 | NQ       | SELL_LIMIT | 2026.08.05 09:25:00 | 29854.6  | 29863.6  | 29832.1  | WIN       |        2.392 |          239.2 |
| TG-MODEL-SE-JSR-02-XAU-20260106-1035-003 | MODEL-SE-JSR-02 | XAUUSD_o | SELL_LIMIT | 2026.01.06 10:35:00 |  4467.14 |  4476.94 |  4447.54 | WIN       |        1.99  |          199   |
| TG-MODEL-ISB-PC-01-NQ-20260805-1410-004  | MODEL-ISB-PC-01 | NQ       | BUY_LIMIT  | 2026.08.05 14:10:00 | 29747.8  | 29732.5  | 29801.3  | EXPIRED   |        0     |            0   |
| TG-MODEL-ISB-PC-01-NQ-20260806-1410-005  | MODEL-ISB-PC-01 | NQ       | SELL_LIMIT | 2026.08.06 14:10:00 | 29349.6  | 29369.7  | 29279.2  | LOSS      |       -1     |         -100   |
| TG-MODEL-SMT-CD-03-NQ-20260806-1420-006  | MODEL-SMT-CD-03 | NQ       | BUY_LIMIT  | 2026.08.06 14:20:00 | 29288.8  | 29246.7  | 29394    | BREAKEVEN |        0     |            0   |
| TG-MODEL-ISB-PC-01-NQ-20260807-1410-007  | MODEL-ISB-PC-01 | NQ       | BUY_LIMIT  | 2026.08.07 14:10:00 | 29504.8  | 29479.5  | 29593.3  | WIN       |        3.461 |          346.1 |
| TG-MODEL-SE-JSR-02-XAU-20260109-1415-008 | MODEL-SE-JSR-02 | XAUUSD_o | SELL_LIMIT | 2026.01.09 14:15:00 |  4474.15 |  4481.64 |  4459.17 | BREAKEVEN |        0.016 |            0   |
| TG-MODEL-ISB-PC-01-NQ-20260812-1535-009  | MODEL-ISB-PC-01 | NQ       | BUY_LIMIT  | 2026.08.12 15:35:00 | 29733.1  | 29718.1  | 29785.6  | EXPIRED   |        0     |            0   |
| TG-MODEL-ISB-PC-01-NQ-20260814-1535-010  | MODEL-ISB-PC-01 | NQ       | BUY_LIMIT  | 2026.08.14 15:35:00 | 30132.2  | 30116.9  | 30185.8  | BREAKEVEN |        0     |            0   |
| TG-MODEL-SMT-CD-03-NQ-20260817-1015-011  | MODEL-SMT-CD-03 | NQ       | SELL_LIMIT | 2026.08.17 10:15:00 | 30207.2  | 30233.5  | 30141.5  | BREAKEVEN |        0     |            0   |
| TG-MODEL-ISB-PC-01-NQ-20260820-1435-012  | MODEL-ISB-PC-01 | NQ       | SELL_LIMIT | 2026.08.20 14:35:00 | 29355    | 29372.7  | 29293    | BREAKEVEN |        0     |            0   |
| TG-MODEL-SMT-CD-03-NQ-20260826-1635-013  | MODEL-SMT-CD-03 | NQ       | BUY_LIMIT  | 2026.08.26 16:35:00 | 29093.6  | 29080.6  | 29126.1  | WIN       |        2.425 |          242.5 |
| TG-MODEL-ISB-PC-01-NQ-20260902-1410-014  | MODEL-ISB-PC-01 | NQ       | SELL_LIMIT | 2026.09.02 14:10:00 | 28912.6  | 28948.9  | 28785.5  | LOSS      |       -1     |         -100   |
| TG-MODEL-SMT-CD-03-NQ-20260908-0810-015  | MODEL-SMT-CD-03 | NQ       | SELL_LIMIT | 2026.09.08 08:10:00 | 29694.7  | 29725.1  | 29618.7  | WIN       |        2.467 |          246.7 |
| TG-MODEL-SMT-CD-03-NQ-20260916-1540-016  | MODEL-SMT-CD-03 | NQ       | SELL_LIMIT | 2026.09.16 15:40:00 | 29110.8  | 29132.5  | 29056.5  | EXPIRED   |        0     |            0   |
| TG-MODEL-SMT-CD-03-NQ-20260922-0850-017  | MODEL-SMT-CD-03 | NQ       | BUY_LIMIT  | 2026.09.22 08:50:00 | 30517.2  | 30474.6  | 30623.7  | LOSS      |       -1     |         -100   |
| TG-MODEL-SMT-CD-03-NQ-20260925-1520-018  | MODEL-SMT-CD-03 | NQ       | SELL_LIMIT | 2026.09.25 15:20:00 | 30672.4  | 30697.8  | 30608.9  | EXPIRED   |        0     |            0   |
| TG-MODEL-SMT-CD-03-NQ-20260928-0940-019  | MODEL-SMT-CD-03 | NQ       | BUY_LIMIT  | 2026.09.28 09:40:00 | 30317.4  | 30304.9  | 30348.7  | BREAKEVEN |        0     |            0   |
| TG-MODEL-SMT-CD-03-NQ-20260928-1640-020  | MODEL-SMT-CD-03 | NQ       | SELL_LIMIT | 2026.09.28 16:40:00 | 30413.9  | 30432.5  | 30367.4  | EXPIRED   |        0     |            0   |
