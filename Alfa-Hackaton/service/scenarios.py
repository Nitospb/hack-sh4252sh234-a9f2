"""Deterministic simple-interest and FX comparisons from explicit user inputs."""
from decimal import Decimal,InvalidOperation,ROUND_HALF_UP


def number(data,key,low,high):
    value=data.get(key)
    if isinstance(value,bool) or not isinstance(value,(str,int,float)) or len(str(value))>40:raise ValueError('Укажите число: '+key)
    try:d=Decimal(str(value).replace(',','.'))
    except InvalidOperation:raise ValueError('Неверное число: '+key) from None
    if not d.is_finite() or not Decimal(str(low))<=d<=Decimal(str(high)):raise ValueError('Число вне допустимого диапазона: '+key)
    return d


def money(value):return str(value.quantize(Decimal('.01'),rounding=ROUND_HALF_UP))


def calculate(data):
    if not isinstance(data,dict):raise ValueError('Ожидаются параметры сценария')
    if data.get('acknowledge_assumptions') is not True:raise ValueError('Подтвердите допущения расчёта')
    kind=data.get('kind');currency=data.get('currency','')
    if currency not in ('RUB','USD','EUR','CNY'):raise ValueError('Укажите валюту')
    if kind=='loan':
        principal=number(data,'principal',0,10**15);days=number(data,'days',1,3660)
        if days!=days.to_integral_value():raise ValueError('Дни должны быть целым числом')
        basis=data.get('basis')
        if type(basis) is not int or basis not in (360,365):raise ValueError('Укажите базу360 или365 дней')
        rate_type=data.get('rate_type')
        if rate_type=='fixed':
            baseline=scenario=number(data,'fixed_rate',0,100)
            explanation='Фиксированная ставка сохраняется в обоих сценариях на весь указанный период.'
            normalized={'fixed_rate':str(baseline)}
        elif rate_type=='floating':
            initial=number(data,'benchmark_base',0,100);alternative=number(data,'benchmark_scenario',0,100)
            spread=number(data,'spread',-30,100);baseline=initial+spread;scenario=alternative+spread
            if baseline<0 or scenario<0 or max(baseline,scenario)>100:raise ValueError('Итоговая ставка должна быть от0 до100%')
            explanation='Ставка равна введённому индексу плюс спред; каждый индекс действует весь период.'
            normalized={'benchmark_base':str(initial),'benchmark_scenario':str(alternative),'spread':str(spread)}
        else:raise ValueError('Укажите фиксированную или плавающую ставку')
        base=principal*baseline/100*days/basis;alt=principal*scenario/100*days/basis
        return {'kind':kind,'currency':currency,'base':money(base),'scenario':money(alt),'delta':money(alt-base),
                'metric':'Процентные расходы','formula':'principal × annual_rate / 100 × days / basis',
                'inputs':{'principal':str(principal),'days':int(days),'basis':basis,'rate_type':rate_type,**normalized},
                'assumptions':[explanation,'Простые проценты и постоянный остаток долга; погашения, комиссии, налоги и капитализация не учитываются.',
                               'Условия заданы пользователем и не подтверждены банком. Это сравнение сценариев, не прогноз ставки.']}
    if kind=='fx':
        amount=number(data,'amount',0,10**15);base_rate=number(data,'rate_base',Decimal('.000001'),10**6);alt_rate=number(data,'rate_scenario',Decimal('.000001'),10**6)
        flow=data.get('flow')
        if flow not in ('revenue','expense'):raise ValueError('Укажите доход или расход')
        if currency=='RUB':raise ValueError('Для FX укажите иностранную валюту')
        base=amount*base_rate;alt=amount*alt_rate
        return {'kind':kind,'currency':'RUB','base':money(base),'scenario':money(alt),'delta':money(alt-base),
                'cash_effect_delta':money((alt-base)*(1 if flow=='revenue' else -1)),
                'metric':'Рублёвый эквивалент '+('дохода' if flow=='revenue' else 'расхода'),
                'formula':'foreign_amount × RUB_per_foreign_unit',
                'inputs':{'amount':str(amount),'foreign_currency':currency,'rate_base':str(base_rate),'rate_scenario':str(alt_rate),'flow':flow},
                'assumptions':['Курс указан в рублях за одну единицу иностранной валюты; объём одинаков в обоих сценариях.',
                               'Хеджирование, комиссии, налоги и сроки платежей не учитываются.',
                               'Объём и курсы введены пользователем, не являются банковским прогнозом.']}
    raise ValueError('Неизвестный вид сценария')
