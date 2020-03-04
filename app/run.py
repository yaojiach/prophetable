import pandas as pd
from prophetable import Prophetable

# p = Prophetable(config='data/config.full.json')
p = Prophetable(config='data/config.outliers.json')
p.run()
print(p.data[
    (
        p.data['ds'] >= pd.to_datetime('2009-12-28', infer_datetime_format=True)
    ) & (
        p.data['ds'] <= pd.to_datetime('2011-01-03', infer_datetime_format=True)
    )
])
print(p.forecast.tail())

try:
    print('Check seasonalities')
    print(p.model.seasonalities)
except:
    print('No seasonalities')

try:
    print('Check built-in holidays')
    print(p.model.train_holiday_names)
except:
    print('No built-in holidays')

try:
    print('Check custom holidays')
    print(
        p.forecast[
            (p.forecast['playoff'] + p.forecast['superbowl']).abs() > 0
        ][['ds', 'playoff', 'superbowl']][-10:]
    )
except:
    print('No custom holidays')
