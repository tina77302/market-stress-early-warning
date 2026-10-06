import {
  Activity,
  BrainCircuit,
  Database,
  FlaskConical,
  GitBranch,
  SearchCheck,
  ShieldCheck,
  Target,
  TrendingUp,
  TriangleAlert,
} from 'lucide-react';


const FEATURES = {
  Equity: [
    'SPY 1D Return',
    'SPY 5D Return',
    'SPY 20D Return',
    'SPY 20D Volatility',
    'SPY 60D Volatility',
    'SPY Drawdown',
    'SPY 20D Momentum',
  ],
  Volatility: [
    'VIX Level',
    'VIX 1D Change',
    'VIX 5D Change',
    'VIX 20D Momentum',
    'VIX 252D Z-Score',
  ],
  Credit: [
    'BAA–Treasury Spread Level',
    'Credit 1D Change',
    'Credit 5D Change',
    'Credit 20D Momentum',
    'Credit 252D Z-Score',
  ],
};


const STEPS = [
  {
    number: '01',
    title: 'Market Data',
    text: 'SPY, VIX and the BAA–Treasury spread provide equity, volatility and credit-market information.',
  },
  {
    number: '02',
    title: 'Stress Index',
    text: 'Past-only rolling standardization combines equity, volatility and credit stress into an equal-weighted Market Stress Index.',
  },
  {
    number: '03',
    title: '10-Day Target',
    text: 'The target equals 1 when at least one defined Stress Event occurs during the next 10 trading days.',
  },
  {
    number: '04',
    title: 'Feature Engineering',
    text: 'Seventeen features capture market returns, volatility, drawdown, momentum, VIX dynamics and credit-spread conditions.',
  },
  {
    number: '05',
    title: 'Purged Walk-Forward',
    text: 'Models are evaluated chronologically with expanding training windows and a 10-trading-day label-overlap purge.',
  },
  {
    number: '06',
    title: 'Risk Intelligence',
    text: 'Out-of-sample risk scores support historical validation, while the fitted deployment model produces the latest score and SHAP drivers.',
  },
];


export default function MethodologyPage() {
  return (
    <div className="space-y-6">

      {/* Header */}
      <div className="bg-dark-card border border-dark-border rounded-lg p-6">
        <div className="flex flex-col xl:flex-row xl:items-end justify-between gap-5">
          <div>
            <div className="flex items-center gap-2 text-financial-blue mb-3">
              <FlaskConical className="w-4 h-4" />
              <span className="text-xs font-semibold tracking-[0.18em]">
                RESEARCH METHODOLOGY
              </span>
            </div>

            <h1 className="text-2xl md:text-3xl font-bold text-white tracking-tight">
              U.S. Financial Market Stress Early Warning
            </h1>

            <p className="text-sm text-gray-400 mt-3 max-w-4xl leading-relaxed">
              Can currently observable financial-market information provide
              an early warning of a U.S. financial-market Stress Event
              occurring within the next 10 trading days?
            </p>
          </div>

          <div className="text-xs font-mono text-gray-500 border border-dark-border rounded px-4 py-3">
            FORECAST HORIZON
            <span className="text-white font-bold ml-3">
              10 TRADING DAYS
            </span>
          </div>
        </div>
      </div>


      {/* Research Pipeline */}
      <div className="bg-dark-card border border-dark-border rounded-lg p-6">
        <div className="mb-5">
          <h2 className="text-sm font-bold text-gray-200 tracking-wider">
            RESEARCH PIPELINE
          </h2>

          <p className="text-xs text-gray-500 mt-1">
            Point-in-time design from raw market information to model-based risk intelligence
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {STEPS.map((step) => (
            <div
              key={step.number}
              className="border border-dark-border rounded-lg p-4"
            >
              <div className="text-[11px] font-mono text-financial-blue">
                STEP {step.number}
              </div>

              <div className="text-sm font-bold text-gray-200 mt-2">
                {step.title}
              </div>

              <p className="text-xs text-gray-500 mt-2 leading-relaxed">
                {step.text}
              </p>
            </div>
          ))}
        </div>
      </div>


      {/* Stress + Target */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">

        <div className="bg-dark-card border border-dark-border rounded-lg p-6">
          <div className="flex items-center gap-2 mb-4">
            <Activity className="w-4 h-4 text-financial-red" />

            <h2 className="text-sm font-bold text-gray-200 tracking-wider">
              STRESS EVENT DEFINITION
            </h2>
          </div>

          <p className="text-xs text-gray-500 leading-relaxed">
            Market stress is defined as a broad-market condition rather than
            a simple future SPY decline. The index combines three distinct
            dimensions of financial stress.
          </p>

          <div className="space-y-3 mt-5">
            <div className="border border-dark-border rounded p-4">
              <div className="text-xs font-bold text-gray-200">
                EQUITY STRESS
              </div>
              <div className="text-xs text-gray-500 mt-1">
                Negative 21-trading-day SPY return
              </div>
            </div>

            <div className="border border-dark-border rounded p-4">
              <div className="text-xs font-bold text-gray-200">
                VOLATILITY STRESS
              </div>
              <div className="text-xs text-gray-500 mt-1">
                VIX level
              </div>
            </div>

            <div className="border border-dark-border rounded p-4">
              <div className="text-xs font-bold text-gray-200">
                CREDIT STRESS
              </div>
              <div className="text-xs text-gray-500 mt-1">
                Moody&apos;s Baa corporate yield minus 10-Year U.S. Treasury yield
              </div>
            </div>
          </div>

          <p className="text-[11px] text-gray-500 mt-4 leading-relaxed">
            Each component is standardized against its own past distribution
            using a 252-trading-day rolling window shifted by one observation.
            The three standardized components receive equal weights.
          </p>
        </div>


        <div className="bg-dark-card border border-dark-border rounded-lg p-6">
          <div className="flex items-center gap-2 mb-4">
            <Target className="w-4 h-4 text-financial-amber" />

            <h2 className="text-sm font-bold text-gray-200 tracking-wider">
              FORWARD TARGET
            </h2>
          </div>

          <div className="border border-dark-border rounded-lg p-5 bg-dark-bg/40">
            <div className="text-[11px] text-gray-500">
              TARGET AT DATE t
            </div>

            <div className="text-xl font-bold text-white mt-2">
              Target₁₀D(t) = 1
            </div>

            <p className="text-xs text-gray-400 mt-3 leading-relaxed">
              if at least one Stress Event occurs during trading days
              t+1 through t+10; otherwise the target equals 0.
            </p>
          </div>

          <div className="mt-5 space-y-4">
            <div className="flex gap-3">
              <ShieldCheck className="w-4 h-4 text-financial-green shrink-0 mt-0.5" />

              <div>
                <div className="text-xs font-bold text-gray-200">
                  Past-only threshold
                </div>
                <p className="text-xs text-gray-500 mt-1 leading-relaxed">
                  Stress thresholds are estimated using information available
                  up to that point rather than full-sample future information.
                </p>
              </div>
            </div>

            <div className="flex gap-3">
              <TriangleAlert className="w-4 h-4 text-financial-amber shrink-0 mt-0.5" />

              <div>
                <div className="text-xs font-bold text-gray-200">
                  Incomplete horizons remain unknown
                </div>
                <p className="text-xs text-gray-500 mt-1 leading-relaxed">
                  Observations without the complete forward 10-day window are
                  not converted into artificial negative labels.
                </p>
              </div>
            </div>
          </div>
        </div>

      </div>


      {/* Features */}
      <div className="bg-dark-card border border-dark-border rounded-lg p-6">
        <div className="flex items-center gap-2 mb-5">
          <Database className="w-4 h-4 text-financial-blue" />

          <div>
            <h2 className="text-sm font-bold text-gray-200 tracking-wider">
              FINAL FEATURE SET — 17 FEATURES
            </h2>

            <p className="text-xs text-gray-500 mt-1">
              Three complementary information channels
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {Object.entries(FEATURES).map(([group, features]) => (
            <div
              key={group}
              className="border border-dark-border rounded-lg p-4"
            >
              <div className="text-xs font-bold text-gray-200 mb-3">
                {group.toUpperCase()} · {features.length}
              </div>

              <div className="space-y-2">
                {features.map((feature) => (
                  <div
                    key={feature}
                    className="text-xs text-gray-500 flex items-center gap-2"
                  >
                    <span className="w-1 h-1 rounded-full bg-gray-600" />
                    {feature}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>


      {/* Validation Design */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">

        <div className="bg-dark-card border border-dark-border rounded-lg p-6">
          <div className="flex items-center gap-2 mb-4">
            <GitBranch className="w-4 h-4 text-financial-green" />

            <h2 className="text-sm font-bold text-gray-200 tracking-wider">
              PURGED WALK-FORWARD VALIDATION
            </h2>
          </div>

          <p className="text-xs text-gray-500 leading-relaxed">
            Random train/test splitting is not used. Training windows expand
            through time and predictions are generated only for subsequent,
            unseen observations.
          </p>

          <div className="mt-5 border border-dark-border rounded-lg p-4">
            <div className="flex flex-wrap items-center gap-2 text-[11px] font-mono">
              <span className="px-3 py-2 bg-gray-800 rounded text-gray-300">
                TRAIN
              </span>

              <span className="text-gray-600">→</span>

              <span className="px-3 py-2 border border-financial-red/40 rounded text-financial-red">
                10D PURGE
              </span>

              <span className="text-gray-600">→</span>

              <span className="px-3 py-2 bg-gray-800 rounded text-gray-300">
                OOS TEST
              </span>

              <span className="text-gray-600">→</span>

              <span className="px-3 py-2 bg-gray-800 rounded text-gray-300">
                EXPAND
              </span>
            </div>
          </div>

          <p className="text-[11px] text-gray-500 mt-4 leading-relaxed">
            The 10-trading-observation gap removes training labels whose
            forward target windows would overlap the beginning of the test
            period. This prevents label leakage across the train/test boundary.
          </p>
        </div>


        <div className="bg-dark-card border border-dark-border rounded-lg p-6">
          <div className="flex items-center gap-2 mb-4">
            <SearchCheck className="w-4 h-4 text-financial-blue" />

            <h2 className="text-sm font-bold text-gray-200 tracking-wider">
              MODEL EVALUATION
            </h2>
          </div>

          <div className="grid grid-cols-2 gap-3">
            {[
              'ROC-AUC',
              'PR-AUC',
              'Precision',
              'Recall',
              'F1 Score',
              'False Alarm Rate',
              'Missed Event Rate',
              'Brier Score',
            ].map((metric) => (
              <div
                key={metric}
                className="border border-dark-border rounded p-3 text-xs text-gray-400"
              >
                {metric}
              </div>
            ))}
          </div>

          <p className="text-[11px] text-gray-500 mt-4 leading-relaxed">
            Logistic Regression serves as the interpretable baseline.
            XGBoost captures nonlinear relationships and feature interactions.
            Model quality is assessed from walk-forward out-of-sample
            predictions rather than in-sample fit.
          </p>
        </div>

      </div>


      {/* Findings */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">

        <div className="bg-dark-card border border-dark-border rounded-lg p-6">
          <TrendingUp className="w-5 h-5 text-financial-green mb-4" />

          <h2 className="text-sm font-bold text-gray-200">
            MODEL COMPARISON
          </h2>

          <p className="text-xs text-gray-500 mt-3 leading-relaxed">
            Logistic Regression achieved stronger OOS discrimination and
            recall, while XGBoost produced lower Brier error and fewer false
            alarms at the fixed 0.5 reference threshold. The models therefore
            show different operating trade-offs. XGBoost is used for current
            deployment and SHAP-based nonlinear interpretation, while Logistic
            Regression remains an important benchmark.
          </p>
        </div>


        <div className="bg-dark-card border border-dark-border rounded-lg p-6">
          <BrainCircuit className="w-5 h-5 text-financial-blue mb-4" />

          <h2 className="text-sm font-bold text-gray-200">
            SHAP EXPLAINABILITY
          </h2>

          <p className="text-xs text-gray-500 mt-3 leading-relaxed">
            SHAP is applied to the fitted XGBoost deployment model to identify
            which current market features push the model output higher or
            lower. SHAP contributions are not interpreted as percentage-point
            changes in event probability.
          </p>
        </div>


        <div className="bg-dark-card border border-dark-border rounded-lg p-6">
          <FlaskConical className="w-5 h-5 text-financial-amber mb-4" />

          <h2 className="text-sm font-bold text-gray-200">
            RATE FEATURE ABLATION
          </h2>

          <p className="text-xs text-gray-500 mt-3 leading-relaxed">
            Four U.S. Treasury-rate and 10Y–2Y yield-curve features were tested
            as a 21-feature extension under the identical purged walk-forward
            OOS framework. Logistic ROC-AUC declined from 0.922 to 0.916 and
            PR-AUC from 0.807 to 0.786; XGBoost ROC-AUC changed only from
            0.899 to 0.901 while PR-AUC declined from 0.779 to 0.773.
            The extension showed no consistent incremental predictive value,
            so the final specification retains 17 features.
          </p>
        </div>

      </div>


      {/* Limitations */}
      <div className="bg-dark-card border border-dark-border rounded-lg p-6">
        <div className="flex items-center gap-2 mb-4">
          <TriangleAlert className="w-4 h-4 text-financial-amber" />

          <h2 className="text-sm font-bold text-gray-200 tracking-wider">
            INTERPRETATION & LIMITATIONS
          </h2>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 text-xs text-gray-500 leading-relaxed">
          <p>
            <span className="text-gray-300 font-bold">
              Risk score ≠ calibrated probability.
            </span>
            {' '}Calibration diagnostics indicate that raw model outputs,
            particularly in intermediate and high-score regions, should not
            be interpreted as literal event probabilities.
          </p>

          <p>
            <span className="text-gray-300 font-bold">
              Credit spread is a proxy.
            </span>
            {' '}The long-history credit measure is the Moody&apos;s Baa
            corporate yield minus the 10-Year Treasury yield. It is not an
            ICE BofA high-yield OAS series.
          </p>

          <p>
            <span className="text-gray-300 font-bold">
              Early warning, not market timing.
            </span>
            {' '}The system estimates broad financial-market stress risk.
            It is not designed as a trading signal or as a direct forecast
            of the future SPY price.
          </p>
        </div>
      </div>

    </div>
  );
}
