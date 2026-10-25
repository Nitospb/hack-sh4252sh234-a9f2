"use client";

import { useClient } from "@/src/providers/ClientProvider";
import PageHeader from "@/src/components/PageHeader/PageHeader";
import Card from "@/src/components/UI/Card/Card";
import Toggle from "@/src/components/UI/Toggle/Toggle";
import SettingRow from "@/src/components/Settings/SettingRow/SettingRow";
import type { FeedSettings } from "@/src/types";
import styles from "@/src/styles/Design.module.css";

const DISPLAY_OPTIONS: [keyof FeedSettings, string, string][] = [
  [
    "opportunities",
    "Показывать возможности",
    "Не только риски, но и шансы для бизнеса",
  ],
  [
    "group",
    "События по компаниям группы",
    "Учитывать контекст всех юрлиц группы",
  ],
  [
    "promotions",
    "Предложения банка в ленте",
    "Продукты, релевантные событию, с пометкой «реклама»",
  ],
];

const NOTIFICATION_OPTIONS: [keyof FeedSettings, string, string][] = [
  ["push", "Push о высоких рисках", "Сразу, как событие обработано"],
  ["digest", "Утренняя сводка", "E-mail в 8:30 по рабочим дням"],
  ["weekly", "Еженедельный обзор", "Итоги недели и прогноз банка"],
  ["telegram", "Telegram-бот Альфа-Бизнес", "Дублировать сводку в мессенджер"],
];

const Settings = () => {
  const { settings, updateSettings } = useClient();
  const renderOption = ([key, label, description]: [
    keyof FeedSettings,
    string,
    string,
  ]) => (
    <SettingRow
      key={key}
      label={label}
      description={description}
      control={
        <Toggle
          label={label}
          checked={Boolean(settings[key])}
          onChange={(checked) => updateSettings({ [key]: checked })}
        />
      }
    />
  );

  return (
    <>
      <PageHeader
        title="Настройки ленты"
        description="Настройки личные для каждого пользователя: у финдиректора и главбуха одной компании ленты могут отличаться."
      />
      <div className={styles.g2}>
        <Card title="Что показывать">
          <SettingRow
            label="Порог значимости"
            description="События ниже порога скрываются в «Низкая значимость»"
          >
            <input
              type="range"
              min={0}
              max={100}
              value={settings.threshold}
              aria-label="Порог значимости"
              onChange={(event) =>
                updateSettings({ threshold: Number(event.target.value) })
              }
            />
            <b>{settings.threshold}%</b>
          </SettingRow>
          {DISPLAY_OPTIONS.map(renderOption)}
        </Card>
        <Card title="Уведомления">
          {NOTIFICATION_OPTIONS.map(renderOption)}
        </Card>
      </div>
    </>
  );
};

export default Settings;
