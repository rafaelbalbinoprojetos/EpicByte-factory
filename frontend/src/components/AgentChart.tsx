import {useEffect, useRef} from 'react';
import * as echarts from 'echarts/core';
import {BarChart} from 'echarts/charts';
import {GridComponent, TooltipComponent} from 'echarts/components';
import {CanvasRenderer} from 'echarts/renderers';
import {Empty} from '@/components/ui/panel';
import {AGENT_LABELS} from '@/lib/format';
import type {Execution} from '@/lib/types';

echarts.use([BarChart, GridComponent, TooltipComponent, CanvasRenderer]);

/** Execuções persistidas por agente. Sem dados reais, não desenha nada. */
export function AgentChart({executions}: {executions: Execution[]}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current || !executions.length) return;
    const chart = echarts.init(ref.current);
    const agents = Object.keys(AGENT_LABELS).filter(a => executions.some(e => e.agent === a));
    chart.setOption({
      backgroundColor: 'transparent',
      textStyle: {fontFamily: 'Inter Variable, Segoe UI, sans-serif'},
      grid: {left: 35, right: 15, top: 20, bottom: 45},
      tooltip: {trigger: 'axis', backgroundColor: '#101925', borderColor: '#223145', textStyle: {color: '#dce6f3'}},
      xAxis: {type: 'category', data: agents.map(a => AGENT_LABELS[a]), axisLabel: {color: '#8193a7', fontSize: 10, rotate: 15}, axisLine: {lineStyle: {color: '#263445'}}},
      yAxis: {type: 'value', minInterval: 1, axisLabel: {color: '#8193a7'}, splitLine: {lineStyle: {color: '#1e2938'}}},
      series: [{name: 'Execuções persistidas', type: 'bar', barMaxWidth: 26, data: agents.map(a => executions.filter(e => e.agent === a).length), itemStyle: {color: '#31c5dd', borderRadius: [4, 4, 0, 0]}}],
    });
    const resize = () => chart.resize();
    window.addEventListener('resize', resize);
    return () => {
      window.removeEventListener('resize', resize);
      chart.dispose();
    };
  }, [executions]);
  return executions.length ? <div ref={ref} className="h-[230px]" /> : <Empty>Sem execuções para construir métricas.</Empty>;
}
