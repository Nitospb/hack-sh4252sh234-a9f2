"use client";

import { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import Avatar from "@/src/components/UI/Avatar/Avatar";
import Badge from "@/src/components/UI/Badge/Badge";
import Button from "@/src/components/UI/Button/Button";
import Card from "@/src/components/UI/Card/Card";
import DataTable from "@/src/components/UI/DataTable/DataTable";
import Drawer from "@/src/components/UI/Drawer/Drawer";
import Empty from "@/src/components/UI/Empty/Empty";
import FilterPills from "@/src/components/UI/FilterPills/FilterPills";
import Icon, { type IconName } from "@/src/components/UI/Icon/Icon";
import InfoBox from "@/src/components/UI/InfoBox/InfoBox";
import KeyValueList from "@/src/components/UI/KeyValueList/KeyValueList";
import StatCard from "@/src/components/UI/StatCard/StatCard";
import Toggle from "@/src/components/UI/Toggle/Toggle";
import TextField from "@/src/components/UI/TextField/TextField";
import s from "./Kit.module.css";

const sections = [
  ["foundation", "Основа"],
  ["actions", "Действия"],
  ["inputs", "Ввод и выбор"],
  ["content", "Данные и контент"],
  ["feedback", "Состояния"],
] as const;

const colors = [
  ["Акцент", "--color-light-accent-primary", "#EF3124"],
  ["Текст", "--color-light-neutral-1500", "#121213"],
  ["Поверхность", "--color-light-base-bg-primary", "#FFFFFF"],
  ["Фон", "--color-light-base-bg-secondary", "#F2F3F5"],
  ["Граница", "--color-light-neutral-300", "#E7E8EB"],
  ["Второй акцент", "--color-light-accent-secondary", "#212124"],
  ["Успех", "--color-light-text-positive", "#0D9336"],
  ["Фокус", "--color-light-status-info", "#2288FA"],
] as const;

const icons: IconName[] = ["home", "news", "search", "chart", "document", "user", "settings", "star"];

function SectionHeading({ number, title, description }: { number: string; title: string; description: string }) {
  return (
    <div className={s.sectionHeading}>
      <span className={s.sectionNumber}>{number}</span>
      <div><h2>{title}</h2><p>{description}</p></div>
    </div>
  );
}

function Sample({ title, path, children }: { title: string; path?: string; children: React.ReactNode }) {
  return (
    <div className={s.sample}>
      <div className={s.sampleHead}><h3>{title}</h3>{path && <code>{path}</code>}</div>
      <div className={s.sampleBody}>{children}</div>
    </div>
  );
}

export default function Kit() {
  const [filter, setFilter] = useState("all");
  const [enabled, setEnabled] = useState(true);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [query, setQuery] = useState("");

  return (
    <div className={s.kit}>
      <header className={s.hero}>
        <div className={s.eyebrow}><span className={s.spark} /> АЛЬФА-БИЗНЕС / UI KIT <span>CORE REFERENCE</span></div>
        <div className={s.heroGrid}>
          <div>
            <h1>Библиотека<br /><em>компонентов.</em></h1>
            <p>Визуальный язык новостной аналитики на основе публичной дизайн-системы Альфа-Банка. Общие токены и компоненты используются в приложении.</p>
          </div>
          <div className={s.heroMark} aria-hidden="true"><Image src="/alfa-bank-logo.svg" width={112} height={112} alt="" unoptimized /><small>CORE / 01</small></div>
        </div>
        <div className={s.heroFoot}><a href="https://core-ds.github.io/core-components/master/?path=/docs/components-overview--docs" target="_blank" rel="noreferrer">Официальный Core Components ↗</a><Link href="/feed">Перейти в продукт <span aria-hidden="true">↗</span></Link></div>
      </header>

      <nav className={s.sectionNav} aria-label="Разделы библиотеки">
        {sections.map(([id, label], index) => <a key={id} href={`#${id}`}><span>0{index + 1}</span>{label}</a>)}
      </nav>

      <section id="foundation" className={s.section}>
        <SectionHeading number="01" title="Основа" description="Публичная палитра Core: красный акцент, почти чёрный текст, белые и серые поверхности. Для статусов сохраняем текстовые подписи." />
        <div className={s.foundationGrid}>
          <Sample title="Цветовые токены" path="styles/alfa-tokens.css">
            <div className={s.swatches}>{colors.map(([label, token, hex]) => <div className={s.swatch} key={token}><span className={s.swatchColor} style={{ background: `var(${token})` }} /><span><b>{label}</b><small>{token} · {hex}</small></span></div>)}</div>
          </Sample>
          <Sample title="Типографика" path="system-ui">
            <div className={s.typeRamp}>
              <div><span>Headline L</span><strong className={s.display}>Ясно о главном</strong></div>
              <div><span>Headline S</span><strong className={s.heading}>Влияние на бизнес</strong></div>
              <div><span>Paragraph M</span><p>Факты, допущения и возможные последствия — в понятной последовательности.</p></div>
              <div><span>Caption</span><small>Источник · дата · статус проверки</small></div>
            </div>
          </Sample>
        </div>
        <div className={s.ruleRow}><span>Отступы: 4 / 8 / 12 / 16 / 24 / 32</span><span>Радиусы: 8 / 10 / 12 / 16 / 24</span><span>Контролы: 32 / 40 / 48 / 56 px</span><span>Фокус: #2288FA</span></div>
      </section>

      <section id="actions" className={s.section}>
        <SectionHeading number="02" title="Действия" description="Иерархия Core: красная accent, чёрная primary, серая secondary, контурная и текстовая кнопки." />
        <div className={s.twoColumns}>
          <Sample title="Кнопки" path="UI/Button">
            <div className={s.buttonRow}>
              <Button variant="primary" onClick={() => setDrawerOpen(true)}>Accent <span aria-hidden="true">↗</span></Button>
              <Button variant="dark" onClick={() => setDrawerOpen(true)}>Primary</Button>
              <Button onClick={() => setDrawerOpen(true)}>Secondary</Button>
              <Button variant="outline" onClick={() => setDrawerOpen(true)}>Outlined</Button>
              <Button variant="text" onClick={() => setDrawerOpen(true)}>Text</Button>
              <Button disabled>Недоступна</Button>
            </div>
            <div className={s.buttonSizes}><span>Размеры</span><Button size={32} variant="dark" onClick={() => setDrawerOpen(true)}>32</Button><Button size={40} variant="dark" onClick={() => setDrawerOpen(true)}>40</Button><Button size={48} variant="dark" onClick={() => setDrawerOpen(true)}>48</Button><Button size={56} variant="dark" onClick={() => setDrawerOpen(true)}>56</Button></div>
            <p className={s.helper}>Нажатие открывает боковую панель. В приложении сохранены прежние имена вариантов API; визуально они соответствуют Core.</p>
          </Sample>
          <Sample title="Пиктограммы" path="react-iconly · light">
            <div className={s.iconGrid}>{icons.map(name => <div key={name}><Icon name={name} size={20} /><small>{name}</small></div>)}</div>
            <p className={s.helper}>Иконка дополняет подпись; смысл действия не зависит от рисунка.</p>
          </Sample>
        </div>
      </section>

      <section id="inputs" className={s.section}>
        <SectionHeading number="03" title="Ввод и выбор" description="Явные подписи, выбранное состояние и понятный фокус помогают работать с длинным аналитическим сценарием." />
        <div className={s.twoColumns}>
          <Sample title="Фильтры" path="UI/FilterPills">
            <FilterPills label="Показать материалы" options={[{value:"all",label:"Все"},{value:"news",label:"Новости"},{value:"bank",label:"Аналитика банка"}]} value={filter} onChange={setFilter} />
            <p className={s.selection}>Выбрано: <strong>{filter === "all" ? "Все" : filter === "news" ? "Новости" : "Аналитика банка"}</strong></p>
          </Sample>
          <Sample title="Переключатель" path="UI/Toggle">
            <div className={s.toggleRow}><div><strong>Учитывать интересы компании</strong><p>Пример локального состояния компонента</p></div><Toggle label="Учитывать интересы компании" checked={enabled} onChange={setEnabled} /></div>
            <span className={s.selection}>{enabled ? "Включено" : "Выключено"}</span>
          </Sample>
          <Sample title="Поле ввода" path="UI/TextField">
            <TextField id="kit-search" type="search" label="Поиск по новостям" value={query} onChange={setQuery} placeholder="Тема, компания или событие" hint="Введите название события или компании" leadingIcon={<Icon name="search" size={20} />} />
            <p className={s.helper} aria-live="polite">{query ? `Запрос: ${query}` : "Десктоп: подпись внутри поля · мобильный: снаружи."}</p>
          </Sample>
          <Sample title="Состояния поля" path="UI/TextField">
            <div className={s.fieldStates}>
              <TextField id="kit-error" label="Период" value="" onChange={() => {}} placeholder="Укажите период" error="Укажите период анализа" />
              <TextField id="kit-disabled" label="Недоступное поле" value="Только просмотр" onChange={() => {}} disabled />
            </div>
          </Sample>
        </div>
      </section>

      <section id="content" className={s.section}>
        <SectionHeading number="04" title="Данные и контент" description="Компоненты сохраняют различие между фактом, оценкой модели и позицией банка." />
        <div className={s.twoColumns}>
          <Sample title="Статусы и метки" path="UI/Badge">
            <div className={s.badgeRow}><Badge tone="risk">Риск</Badge><Badge tone="opp">Возможность</Badge><Badge tone="watch">Требует проверки</Badge><Badge tone="fact">Факт</Badge><Badge tone="bank">Позиция банка</Badge><Badge tone="ai">Оценка AI</Badge><Badge tone="gray">Нейтрально</Badge></div>
          </Sample>
          <Sample title="Аватар и идентичность" path="UI/Avatar">
            <div className={s.identity}><Avatar text="Б" size={48} background="var(--color-light-accent-secondary)" radius="14px" /><div><strong>Бизнес-контекст</strong><small>Обезличенный профиль</small></div></div>
          </Sample>
          <Sample title="Карточка" path="UI/Card">
            <Card title="Разбор события" action={<Badge tone="ai">Оценка AI</Badge>}><p className={s.cardText}>Короткий вывод, затем основания и переход к подробностям. Для реального события здесь показываются подтверждённые источники.</p><Button variant="outline" href="/feed">Открыть ленту</Button></Card>
          </Sample>
          <Sample title="Показатель" path="UI/StatCard">
            <div className={s.stats}><StatCard label="Материалы" value="12" detail="Пример отображения" compact /><StatCard label="Новые" value="3" detail="За период" trend="positive" compact /></div>
            <p className={s.helper}>Числа на этой странице демонстрационные и не связаны с текущим каталогом.</p>
          </Sample>
          <Sample title="Разделение оснований" path="UI/InfoBox">
            <div className={s.infoStack}><InfoBox title="Позиция банка" tone="bank">Подтверждённая цитата из материала банка с указанием страницы.</InfoBox><InfoBox title="Оценка AI" tone="ai">Условное влияние на компанию с явными допущениями.</InfoBox></div>
          </Sample>
          <Sample title="Пары значений" path="UI/KeyValueList">
            <KeyValueList items={[["Компания", "Обезличенный профиль"],["Источник", "Открытая публикация"],["Проверка", <Badge key="checked" tone="watch">На рассмотрении</Badge>]]} />
          </Sample>
        </div>
        <Sample title="Таблица" path="UI/DataTable">
          <DataTable caption="Пример таблицы статусов" headers={["Слой", "Что показывает", "Статус"]} rows={[["Факт", "Сведения из источника", <Badge key="fact" tone="fact">Проверен</Badge>],["Вывод", "Возможное влияние на бизнес", <Badge key="ai" tone="ai">Условно</Badge>],["Контекст", "Данные со слов пользователя", <Badge key="context" tone="watch">Уточняется</Badge>]]} />
        </Sample>
      </section>

      <section id="feedback" className={s.section}>
        <SectionHeading number="05" title="Состояния" description="Пустой результат, ожидание и необходимость проверки объясняют следующий шаг без потери контекста." />
        <div className={s.stateGrid}>
          <div className={s.emptyExample}><span className={s.microLabel}>UI/EMPTY</span><Empty title="Пока нет материалов" description="Измените фильтр или выберите другую компанию, чтобы продолжить поиск." icon="document" action={<Button variant="outline" href="/clients">Выбрать компанию</Button>} /></div>
          <div className={s.stateCard}><span className={`${s.stateIcon} ${s.loadingIcon}`} aria-hidden="true" /><h3>Готовим разбор</h3><p>Показываем этап выполнения и сохраняем доступ к первоисточнику.</p><div className={s.skeleton} aria-hidden="true"><i /><i /><i /></div></div>
          <div className={s.stateCard}><span className={`${s.stateIcon} ${s.warningIcon}`}>!</span><h3>Нужна проверка</h3><p>Недостаточно данных для точного числа. Условный сценарий остаётся доступным.</p><Badge tone="watch">Требует контекста</Badge></div>
        </div>
        <div className={s.drawerCallout}><div><span className={s.microLabel}>OVERLAY / UI/DRAWER</span><h3>Sheet</h3><p>Появляется справа, на телефоне — снизу. Закрывается кнопкой, Escape, нажатием вне панели или свайпом вниз.</p></div><Button variant="dark" onClick={() => setDrawerOpen(true)}>Открыть пример <Icon name="arrow" size={16} /></Button></div>
      </section>

      <footer className={s.footer}><span>ALFA / COMPONENT LIBRARY</span><span>Основано на публичном Core Components. Локальные смысловые метки и сценарии аналитики — адаптация продукта.</span><a href="https://github.com/core-ds/core-components/tree/master/packages/vars/src" target="_blank" rel="noreferrer">Токены Core ↗</a></footer>

      <Drawer id="kit-drawer" label="Пример Sheet" open={drawerOpen} onClose={() => setDrawerOpen(false)} closeLabel="Закрыть пример" side="right" mobileBottom width="min(560px, 100%)">
        <div className={s.drawerContent} data-sheet-scroll><span className={s.microLabel}>КОМПОНЕНТ / DRAWER</span><h2>Подробности без потери контекста</h2><p>Панель подходит для текста новости, источников и дополнительных условий анализа.</p><Card title="Пример содержимого"><p className={s.cardText}>Факт, источник и условный вывод лучше показывать раздельно.</p></Card><Button variant="primary" onClick={() => setDrawerOpen(false)}>Понятно</Button></div>
      </Drawer>
    </div>
  );
}
