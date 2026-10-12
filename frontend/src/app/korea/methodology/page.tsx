import MethodologyOverview from '../../components/MethodologyOverview';

const FEATURES = {
  Equity: [
    'KOSPI 200 1D Return',
    'KOSPI 200 5D Return',
    'KOSPI 200 20D Return',
    'KOSPI 200 20D Volatility',
    'KOSPI 200 60D Volatility',
    'KOSPI 200 Drawdown',
    'KOSPI 200 20D Momentum',
  ],
  Volatility: [
    'VKOSPI Level',
    'VKOSPI 1D Change',
    'VKOSPI 5D Change',
    'VKOSPI 20D Momentum',
    'VKOSPI 252D Z-Score',
  ],
  Credit: [
    'AA− Corporate − Government 3Y Spread Level',
    'Credit 1D Change',
    'Credit 5D Change',
    'Credit 20D Momentum',
    'Credit 252D Z-Score',
  ],
};

export default function MethodologyPage() {
  return <MethodologyOverview market="korea" features={FEATURES}/>;
}
