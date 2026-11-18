import { useEffect, useRef } from 'react'
import {
  CandlestickSeries,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  createChart,
} from 'lightweight-charts'
import type {
  IChartApi,
  ISeriesApi,
  UTCTimestamp,
} from 'lightweight-charts'
import { marketChartKey } from '../../services/marketData'
import type { MarketCandle } from '../../services/marketData'

export type { MarketCandle } from '../../services/marketData'

type Indicator = 'SMA20' | 'EMA20'

type Props = {
  candles: MarketCandle[]
  symbol: string
  marketType: string
  timeframe: string
  indicators: Indicator[]
  autoScale: boolean
  crosshair: boolean
  onLoadOlder: () => void
}

function movingAverage(candles: MarketCandle[], period: number, exponential: boolean) {
  const result: { time: UTCTimestamp; value: number }[] = []
  let average = 0
  let windowSum = 0
  for (let index = 0; index < candles.length; index += 1) {
    const close = candles[index].close
    windowSum += close
    if (index >= period) windowSum -= candles[index - period].close
    if (index < period - 1) continue
    if (index === period - 1) {
      average = windowSum / period
    } else if (exponential) {
      const smoothing = 2 / (period + 1)
      average = close * smoothing + average * (1 - smoothing)
    } else {
      average = windowSum / period
    }
    result.push({ time: candles[index].time as UTCTimestamp, value: average })
  }
  return result
}

export function LiveMarketChart({
  candles,
  symbol,
  marketType,
  timeframe,
  indicators,
  autoScale,
  crosshair,
  onLoadOlder,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const smaSeriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const emaSeriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const dataKeyRef = useRef('')
  const candlesRef = useRef<MarketCandle[]>([])
  const loadOlderRef = useRef(onLoadOlder)

  useEffect(() => {
    loadOlderRef.current = onLoadOlder
  }, [onLoadOlder])

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const chart = createChart(container, {
      width: container.clientWidth,
      height: container.clientHeight,
      layout: {
        background: { color: '#141516' },
        textColor: '#858a8f',
        fontFamily: 'JetBrains Mono, IBM Plex Mono, Consolas, monospace',
        fontSize: 9,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: '#25272a' },
        horzLines: { color: '#25272a' },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: '#858a8f', width: 1, style: 2, visible: true, labelVisible: true },
        horzLine: { color: '#858a8f', width: 1, style: 2, visible: true, labelVisible: true },
      },
      rightPriceScale: {
        borderColor: '#303235',
        autoScale: true,
        scaleMargins: { top: 0.1, bottom: 0.25 },
      },
      timeScale: {
        borderColor: '#303235',
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 4,
        fixLeftEdge: false,
        fixRightEdge: false,
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: false,
      },
      handleScale: {
        axisPressedMouseMove: true,
        mouseWheel: true,
        pinch: true,
      },
      kineticScroll: { mouse: true, touch: true },
    })

    candleSeriesRef.current = chart.addSeries(CandlestickSeries, {
      upColor: '#d9dcde',
      downColor: '#141516',
      borderUpColor: '#d9dcde',
      borderDownColor: '#d9dcde',
      wickUpColor: '#d9dcde',
      wickDownColor: '#d9dcde',
      priceLineColor: '#b5b9bc',
      lastValueVisible: true,
    })
    volumeSeriesRef.current = chart.addSeries(HistogramSeries, {
      priceScaleId: 'volume',
      priceFormat: { type: 'volume' },
      lastValueVisible: false,
      priceLineVisible: false,
    })
    smaSeriesRef.current = chart.addSeries(LineSeries, {
      color: '#a8d9c0',
      lineWidth: 1,
      lastValueVisible: false,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
    })
    emaSeriesRef.current = chart.addSeries(LineSeries, {
      color: '#d99ca5',
      lineWidth: 1,
      lastValueVisible: false,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
    })
    chart.priceScale('volume').applyOptions({
      visible: false,
      scaleMargins: { top: 0.82, bottom: 0 },
    })
    chartRef.current = chart
    const handleVisibleRange = (range: { from: number; to: number } | null) => {
      if (range && range.from < 50) loadOlderRef.current()
    }
    chart.timeScale().subscribeVisibleLogicalRangeChange(handleVisibleRange)

    const resizeObserver = new ResizeObserver(() => {
      if (!containerRef.current || !chartRef.current) return
      chartRef.current.applyOptions({
        width: containerRef.current.clientWidth,
        height: containerRef.current.clientHeight,
      })
    })
    resizeObserver.observe(container)

    return () => {
      resizeObserver.disconnect()
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(handleVisibleRange)
      chart.remove()
      chartRef.current = null
      candleSeriesRef.current = null
      volumeSeriesRef.current = null
      smaSeriesRef.current = null
      emaSeriesRef.current = null
    }
  }, [])

  useEffect(() => {
    const chart = chartRef.current
    const candleSeries = candleSeriesRef.current
    const volumeSeries = volumeSeriesRef.current
    if (!chart || !candleSeries || !volumeSeries) return

    const key = marketChartKey(symbol, marketType, timeframe)
    const previous = candlesRef.current
    const reset = dataKeyRef.current !== key || candles.length < previous.length
    const prepended = !reset
      && previous.length > 0
      && candles.length > previous.length
      && candles[0].time < previous[0].time
    if (reset) {
      candleSeries.setData(candles.map((candle) => ({
        time: candle.time as UTCTimestamp,
        open: candle.open,
        high: candle.high,
        low: candle.low,
        close: candle.close,
      })))
      volumeSeries.setData(candles.map((candle) => ({
        time: candle.time as UTCTimestamp,
        value: candle.volume ?? 0,
        color: candle.close >= candle.open ? '#bfc3c5' : '#666b70',
      })))
      dataKeyRef.current = key
      if (candles.length) chart.timeScale().fitContent()
    } else if (prepended) {
      const visibleRange = chart.timeScale().getVisibleRange()
      candleSeries.setData(candles.map((candle) => ({
        time: candle.time as UTCTimestamp,
        open: candle.open,
        high: candle.high,
        low: candle.low,
        close: candle.close,
      })))
      volumeSeries.setData(candles.map((candle) => ({
        time: candle.time as UTCTimestamp,
        value: candle.volume ?? 0,
        color: candle.close >= candle.open ? '#bfc3c5' : '#666b70',
      })))
      if (visibleRange) chart.timeScale().setVisibleRange(visibleRange)
    } else if (candles.length) {
      const lastPreviousTime = previous.at(-1)?.time ?? 0
      for (const candle of candles) {
        if (candle.time < lastPreviousTime) continue
        candleSeries.update({
          time: candle.time as UTCTimestamp,
          open: candle.open,
          high: candle.high,
          low: candle.low,
          close: candle.close,
        })
        volumeSeries.update({
          time: candle.time as UTCTimestamp,
          value: candle.volume ?? 0,
          color: candle.close >= candle.open ? '#bfc3c5' : '#666b70',
        })
      }
    }
    candlesRef.current = candles
  }, [candles, symbol, marketType, timeframe])

  useEffect(() => {
    smaSeriesRef.current?.setData(
      indicators.includes('SMA20') ? movingAverage(candles, 20, false) : [],
    )
    emaSeriesRef.current?.setData(
      indicators.includes('EMA20') ? movingAverage(candles, 20, true) : [],
    )
  }, [candles, indicators])

  useEffect(() => {
    chartRef.current?.applyOptions({
      rightPriceScale: { autoScale },
      crosshair: {
        vertLine: { visible: crosshair, labelVisible: crosshair },
        horzLine: { visible: crosshair, labelVisible: crosshair },
      },
    })
  }, [autoScale, crosshair])

  return <div ref={containerRef} className="live-market-chart" role="img" aria-label={`${symbol} ${marketType} ${timeframe} Binance candlestick chart`} />
}
