# LG ThinQ · Cockpit de Climatização

O [ConfigMap do dashboard](../../infra/monitoring-dashboards/grafana-dashboard-lg-thinq.yaml) segue o provisionamento do Cockpit Deye. O seletor **Aparelho** usa um nome fixo por dispositivo. Mantenha esse mesmo nome no Prometheus e no PostgreSQL.

## Contrato do exporter

Todas as métricas abaixo usam o rótulo `device`. Inicialize os indicadores de sucesso em zero por aparelho configurado até a primeira consulta bem-sucedida. Use o endpoint de leitura do ThinQ e um Secret para a credencial.

| Métrica | Valor |
|---|---|
| `lg_thinq_power_on` | `POWER_ON` = 1, `POWER_OFF` = 0 |
| `lg_thinq_room_temperature_celsius` | Temperatura atual em °C |
| `lg_thinq_target_temperature_celsius` | Temperatura programada em °C |
| `lg_thinq_device_state_info` | 1, com rótulos `mode`, `fan`, `fan_detail`, `swing`, `display`, `run_state`, `start_timer`, `stop_timer` e `sleep_timer` quando disponíveis |
| `lg_thinq_state_last_success_timestamp_seconds` | Timestamp Unix da última consulta bem-sucedida de estado |
| `lg_thinq_state_collection_success` | Resultado da última consulta de estado, 1 para sucesso, 0 para falha |
| `lg_thinq_energy_collection_success` | Resultado da última consulta de energia, 1 para sucesso, 0 para falha |
| `lg_thinq_filter_used_time_raw` | `filterInfo.usedTime`, na unidade original |
| `lg_thinq_filter_lifetime_raw` | `filterInfo.filterLifetime`, na unidade original |

Os painéis ocultam leituras de estado com cinco minutos ou mais. O modo configurado e o estado interno são exibidos como reportados pela LG. O campo `NORMAL` ainda não foi validado como indicador do compressor.

## Consumo diário

O Grafana consulta a fonte PostgreSQL que o Deye já usa. A tabela abaixo é o contrato para o coletor de consumo. Execute a criação da tabela com o papel responsável pela ingestão e dê ao usuário da fonte de dados do Grafana acesso de leitura.

```sql
CREATE TABLE public.lg_thinq_daily_energy (
    device text NOT NULL,
    day date NOT NULL,
    energy_wh bigint NOT NULL CHECK (energy_wh >= 0),
    PRIMARY KEY (device, day)
);
```

Busque `energyUsage` diário no ThinQ, use `usedDate` como a coluna `day` e faça upsert pela chave `(device, day)`. Preserve as lacunas quando a LG não devolver uma leitura. O painel converte Wh em kWh. A média divide o total somente pelos dias com leitura e a visão mensal respeita o intervalo selecionado.

O piloto confirmou sete dias de consumo retrospectivo. O histórico de estado e temperatura começa com o scrape do exporter. Para testar após o provisionamento, selecione um aparelho e um período com registros e confira se as barras usam a data do consumo e se aparelho desligado aparece como **Desligado**.
