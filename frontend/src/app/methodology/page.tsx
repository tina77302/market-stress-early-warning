import MethodologyOverview from '../components/MethodologyOverview';

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

export default function MethodologyPage() {
  return <MethodologyOverview market="us" features={FEATURES}/>;
}
