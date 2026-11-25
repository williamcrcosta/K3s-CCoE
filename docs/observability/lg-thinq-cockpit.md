# LG ThinQ · Cockpit de Climatização

O [ConfigMap do dashboard](../../infra/monitoring-dashboards/grafana-dashboard-lg-thinq.yaml) segue o provisionamento do Cockpit Deye. O seletor **Aparelho** lista os dispositivos com histórico no PostgreSQL e usa um nome fixo por dispositivo. Mantenha esse mesmo nome no Prometheus e no PostgreSQL.

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

O Grafana consulta a fonte PostgreSQL dedicada **LG ThinQ PostgreSQL**. A tabela abaixo é o contrato para o coletor de consumo. Execute a criação da tabela com o papel responsável pela ingestão e dê ao usuário da fonte de dados do Grafana acesso de leitura.

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

## Importar o histórico do AR - Office

1. No Windows, mantenha o CSV diário `ar-office-consumo-completo.csv`. Crie `ar-office-consumo-mensal.csv` em UTF-8 com cabeçalho `aparelho;mes;consumo_wh` e 12 linhas, de novembro de 2024 a outubro de 2025. Use `AR - Office` na primeira coluna, o primeiro dia do mês em `AAAA-MM-01` na segunda e o total em Wh inteiro na terceira. Multiplique kWh por 1000. Guarde os CSVs fora do Git.
2. Envie os dois CSVs ao seu usuário SSH na VM `rke2-pgdb`. No Windows, a partir da pasta dos arquivos, use:

   ```powershell
   scp .\ar-office-consumo-completo.csv .\ar-office-consumo-mensal.csv USUARIO@192.168.50.30:~/
   ```

3. Na VM, abra a pasta onde estão os dois CSVs. Use o [SQL de importação](../../infra/monitoring-dashboards/sql/lg-thinq-history.sql) da branch do PR. Use o banco dedicado **lg_thinq** e um usuário autorizado a criar e atualizar essas tabelas.

   ```bash
   psql -X -h 127.0.0.1 -U USUARIO_POSTGRES -d lg_thinq -f /caminho/lg-thinq-history.sql
   ```

   A transação valida as 389 datas diárias e os 12 meses antes de gravar. É possível repetir a carga sem duplicar registros.

4. Dê ao papel que o Grafana usa acesso de leitura às tabelas novas, a partir de uma sessão conectada ao banco `lg_thinq`:

   ```sql
   GRANT CONNECT ON DATABASE lg_thinq TO lg_thinq_grafana;
   GRANT USAGE ON SCHEMA public TO lg_thinq_grafana;
   GRANT SELECT ON public.lg_thinq_daily_energy, public.lg_thinq_monthly_energy TO lg_thinq_grafana;
   ```

   Confira os períodos importados antes de ativar o dashboard:

   ```sql
   SELECT count(*), min(day), max(day)
   FROM public.lg_thinq_daily_energy WHERE device = 'AR - Office';

   SELECT count(*), min(month), max(month)
   FROM public.lg_thinq_monthly_energy WHERE device = 'AR - Office';
   ```

   A carga inicial deve mostrar 389 dias, de 2025-11-01 a 2026-11-24, e 12 meses, de 2024-11-01 a 2025-10-01. Compare os totais de novembro de 2025 e outubro de 2026 com os valores mensais já conferidos no ThinQ.

Para ver os totais do app no Grafana, selecione um período que inclua os meses inteiros. A tabela mensal usa uma única fonte por mês. Com cobertura diária completa usa a soma diária. Caso contrário, usa o total mensal importado quando disponível. Os cards de total e média diária continuam baseados nas leituras diárias.

## Fonte de dados do Grafana

Em **Connections → Data sources**, adicione uma fonte **PostgreSQL** com o nome exato **LG ThinQ PostgreSQL**. O dashboard resolve a fonte pelo nome, então o UID pode ser gerado pelo Grafana.

| Campo | Valor |
|---|---|
| Host URL | `192.168.50.30:5432` |
| Database name | `lg_thinq` |
| Username | `lg_thinq_grafana` |
| Password | Senha definida para esse papel, inserida na interface do Grafana |
| TLS/SSL | Use a configuração compatível com o servidor, preferindo a validação do certificado quando configurada |

Use **Save & test** e, depois da importação, confira se o seletor **Aparelho** mostra **AR - Office**. Os painéis de estado e temperatura começam a receber dados quando o exporter estiver em operação.
