import json
import pickle
import pathlib

import pandas as pd
from fbprophet import Prophet

import logging


log_format = 'Prophetable | %(asctime)s | %(name)s | %(levelname)s | %(message)s'
logging.basicConfig(level=logging.DEBUG, format=log_format)
logger = logging.getLogger(__name__)


def _create_parent_dir(full):
    dir_parts = pathlib.PurePath(full).parts[:-1]
    if len(dir_parts) > 0:
        pathlib.Path(*dir_parts).mkdir(parents=True, exist_ok=True)
        logger.debug(f'Created path {pathlib.Path(*dir_parts)}')


class Prophetable:
    """Wrapping fbprophet.Prophet

    # Arguments:

        config: Config file URI
            # Prophetable config:
                # File related
                data_uri: URI for input data, required.
                train_uri: URI for training data, if saving is needed.
                output_uri: URI for forecast output, if saving is needed.
                model_uri: URI for model object, if saving is needed.
                holiday_input_uri: URI for holidays input data in csv, if provided, as opposed to 
                    `holidays` config in Prophet parameters. THis takes priority over `holidays` 
                    config.
                holiday_output_uri: URI for holidays output data in csv, if saving is needed.
                delimiter: The delimiler for input data.

                # Model related
                saturating_min: Maps to `floor` column in Prophet training data.
                saturating_max: Maps to `cap` column in Prophet training data.

            # Mapped directly from Prophet forecaster
                growth: String 'linear' or 'logistic' to specify a linear or logistic trend.
                changepoints: List of dates at which to include potential changepoints. If not 
                    specified, potential changepoints are selected automatically.
                n_changepoints: Number of potential changepoints to include. Not used if input 
                    `changepoints` is supplied. If `changepoints` is not supplied, then 
                    n_changepoints potential changepoints are selected uniformly from the first 
                    `changepoint_range` proportion of the history.
                changepoint_range: Proportion of history in which trend changepoints will be 
                    estimated. Defaults to 0.8 for the first 80%. Not used if `changepoints` is 
                    specified.
                yearly_seasonality: Fit yearly seasonality. Can be 'auto', True, False, or a number
                    of Fourier terms to generate.
                weekly_seasonality: Fit weekly seasonality. Can be 'auto', True, False, or a number 
                    of Fourier terms to generate.
                daily_seasonality: Fit daily seasonality. Can be 'auto', True, False, or a number of
                    Fourier terms to generate.
                holidays: pd.DataFrame with columns holiday (string) and ds (date type) and 
                    optionally columns lower_window and upper_window which specify a range of days 
                    around the date to be included as holidays. lower_window=-2 will include 2 days 
                    prior to the date as holidays. Also optionally can have a column prior_scale 
                    specifying the prior scale for that holiday.
                seasonality_mode: 'additive' (default) or 'multiplicative'.
                seasonality_prior_scale: Parameter modulating the strength of the seasonality model.
                    Larger values allow the model to fit larger seasonal fluctuations, smaller
                    values dampen the seasonality. Can be specified for individual seasonalities 
                    using add_seasonality.
                holidays_prior_scale: Parameter modulating the strength of the holiday components 
                    model, unless overridden in the holidays input.
                changepoint_prior_scale: Parameter modulating the flexibility of the automatic 
                    changepoint selection. Large values will allow many changepoints, small values 
                    will allow few changepoints.
                mcmc_samples: Integer, if greater than 0, will do full Bayesian inference with the 
                    specified number of MCMC samples. If 0, will do MAP estimation.
                interval_width: Float, width of the uncertainty intervals provided for the forecast.
                    If mcmc_samples=0, this will be only the uncertainty in the trend using the MAP 
                    estimate of the extrapolated generative model. If mcmc.samples>0, this will be 
                    integrated over all model parameters, which will include uncertainty in 
                    seasonality.
                uncertainty_samples: Number of simulated draws used to estimate uncertainty 
                    intervals. Settings this value to 0 or False will disable uncertainty estimation
                    and speed up the calculation. uncertainty intervals.
                stan_backend: str as defined in StanBackendEnum default: None - will try to iterate 
                    over all available backends and find the working one
    """
    def __init__(self, config):
        with open(config, 'r') as f:
            self._config = json.load(f)
        
        ## Required file uri
        for attr in ['data_uri']:
            self._get_config(attr)
        
        ## Nullable file uri
        # Intermedairy files will be stored in memory only
        for attr in [
            'train_uri',
            'output_uri',
            'model_uri',
            'holiday_input_uri',
            'holiday_output_uri',
        ]:
            self._get_config(attr, required=False)

        ## Other file related config
        self._get_config('delimiter', default=',', required=False)

        ## Model related config
        self._get_config('ds', default='ds', required=False)
        self._get_config('y', default='y', required=False)
        self._get_config('ts_frequency', default='D', required=False)
        # Modified in make_data()
        self._get_config('min_train_date', default=None, required=False) 
        # Modified in make_data()
        self._get_config('max_train_date', default=None, required=False)
        self._get_config('holidays', default=None, required=False)
        self._get_config('saturating_min', default=None, required=False, type_check=[int, float])
        self._get_config('saturating_max', default=None, required=False, type_check=[int, float])
        # Set the default na_fill to None
        # https://facebook.github.io/prophet/docs/outliers.html
        # Prophet has no problem with missing data. If you set their values to NA in the history but
        # leave the dates in future, then Prophet will give you a prediction for their values.
        self._get_config('na_fill', default=None, required=False, type_check=[int, float])

        ## Mapped directly for Prophet
        self._get_config('growth', default='linear', required=False, type_check=[str])
        self._get_config('changepoints', default=None, required=False, type_check=[list])
        self._get_config('n_changepoints', default=25, required=False, type_check=[int])
        self._get_config('changepoint_range', default=0.8, required=False, type_check=[float, int])
        self._get_config('yearly_seasonality', default='auto', required=False)
        self._get_config('weekly_seasonality', default='auto', required=False)
        self._get_config('daily_seasonality', default='auto', required=False)
        self._get_config('holidays', default=None, required=False)
        self._get_config('seasonality_mode', default='additive', required=False, type_check=[str])
        self._get_config(
            'seasonality_prior_scale', default=10.0, required=False, type_check=[float, int]
        )
        self._get_config(
            'holidays_prior_scale', default=10.0, required=False, type_check=[float, int]
        )
        self._get_config(
            'changepoint_prior_scale', default=0.05, required=False, type_check=[float, int]
        )
        self._get_config('mcmc_samples', default=0, required=False, type_check=[int])
        self._get_config('interval_width', default=0.8, required=False, type_check=[float])
        self._get_config('uncertainty_samples', default=1000, required=False, type_check=[int])
        self._get_config('stan_backend', default=None, required=False, type_check=[str])

        ## Prediction
        self._get_config('future_periods', default=365, required=False, type_check=[int])

        ## Placeholder for other attributes set later
        self.data = None
        self.model = None

    def _get_config(self, attr, required=True, default=None, type_check=None):
        try:
            set_attr = self._config[attr]
            if type_check is not None and set_attr is not None:
                if not any([isinstance(set_attr, t) for t in type_check]):
                    raise TypeError(f'{attr} provided is not {type_check}')
        except KeyError:
            if required:
                raise ValueError(f'{attr} must be provided in config')
            else:       
                set_attr = default
        setattr(self, attr, set_attr)
        logger.info(f'{attr} set to {set_attr}')

    def make_data(self):
        self.data = pd.read_csv(self.data_uri, sep=self.delimiter)
        self.data[self.ds] = pd.to_datetime(self.data[self.ds], infer_datetime_format=True)
        if self.min_train_date is None:
           self.min_train_date =  self.data[self.ds].min()
        if self.max_train_date is None:
           self.max_train_date =  self.data[self.ds].max()
        model_data = pd.DataFrame({
            'ds': pd.date_range(self.min_train_date, self.max_train_date, freq=self.ts_frequency)
        })
        model_data = model_data.merge(
            self.data[[self.ds, self.y]], left_on='ds', right_on=self.ds, how='left'
        )
        if self.ds != 'ds':
            model_data = model_data.drop(columns=[self.ds])
        model_data = model_data.rename(columns={self.y: 'y'})
        if self.na_fill is not None:
            model_data = model_data.fillna(self.na_fill)
        if self.saturating_min is not None:
            model_data['floor'] = self.saturating_min
        if self.saturating_max is not None:
            model_data['cap'] = self.saturating_max
        if self.train_uri is not None:
            _create_parent_dir(self.train_uri)
            model_data.to_csv(self.train_uri, index=False)
            logger.info(f'Training data saved to {self.train_uri}')
        self.data = model_data

    def train(self):
        """Method to train Prophet forecaster
        """
        model = Prophet(
            growth=self.growth,
            changepoints=self.changepoints,
            n_changepoints=self.n_changepoints,
            changepoint_range=self.changepoint_range,
            yearly_seasonality=self.yearly_seasonality,
            weekly_seasonality=self.weekly_seasonality,
            daily_seasonality=self.daily_seasonality,
            holidays=self.holidays,
            seasonality_mode=self.seasonality_mode,
            seasonality_prior_scale=self.seasonality_prior_scale,
            holidays_prior_scale=self.holidays_prior_scale,
            changepoint_prior_scale=self.changepoint_prior_scale,
            mcmc_samples=self.mcmc_samples,
            interval_width=self.interval_width,
            uncertainty_samples=self.uncertainty_samples,
            stan_backend=self.stan_backend
        ).fit(self.data)
        if self.model_uri is not None:
            _create_parent_dir(self.model_uri)
            with open(self.model_uri, 'wb') as f:
                pickle.dump(model, f)
            logger.info(f'Model object saved to {self.model_uri}')
        self.model = model


    def predict(self):
        future = self.model.make_future_dataframe(
            periods=self.future_periods,
            freq=self.ts_frequency
        )
        forecast = self.model.predict(future)
        if self.output_uri is not None:
            _create_parent_dir(self.output_uri)
            forecast.to_csv(self.output_uri, index=False)
            logger.info(f'Forecast output saved to {self.output_uri}')
        self.forecast = forecast
