from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time

from app.features.travel.trips import forecast as fc
from app.features.travel.trips.forecast import a_year_earlier, days_from_daily, pick_mode
from app.features.travel.trips.forecast_service import TripForecastService

TODAY = date(2026, 12, 10)


class TestPickMode:
    def test_forecast_within_two_weeks_of_the_start(self):
        assert pick_mode(date(2026, 12, 20), date(2026, 12, 29), TODAY) == "forecast"

    def test_ongoing_trip_uses_the_forecast(self):
        assert pick_mode(date(2026, 12, 5), date(2026, 12, 29), TODAY) == "forecast"

    def test_far_trip_uses_last_years_climate(self):
        assert pick_mode(date(2027, 3, 1), date(2027, 3, 8), TODAY) == "climate"

    def test_over_trip_has_nothing(self):
        assert pick_mode(date(2026, 11, 1), date(2026, 11, 8), TODAY) == "none"


def test_a_year_earlier_handles_leap_day():
    assert a_year_earlier(date(2028, 2, 29)) == date(2027, 2, 28)
    assert a_year_earlier(date(2027, 3, 1)) == date(2026, 3, 1)


class TestDaysFromDaily:
    def test_rows_are_labelled_with_the_trips_dates_and_rain_has_a_threshold(self):
        daily = {"temperature_2m_min": [1.0, 2.0], "temperature_2m_max": [5.0, 6.0], "precipitation_sum": [0.4, 3.0]}
        days = days_from_daily(daily, [date(2027, 3, 1), date(2027, 3, 2)])
        assert [(d.date, d.min_c, d.max_c, d.rain) for d in days] == [
            (date(2027, 3, 1), 1.0, 5.0, False), (date(2027, 3, 2), 2.0, 6.0, True)]

    def test_missing_columns_become_none(self):
        days = days_from_daily({}, [date(2027, 3, 1)])
        assert days[0].min_c is None and days[0].rain is False


def _stay(city="Beta", lat=None, lng=None, check_in=datetime(2026, 12, 17, 14), check_out=datetime(2026, 12, 19, 10)):
    return SimpleNamespace(place=SimpleNamespace(city=city, country="Testland", lat=lat, lng=lng),
                           check_in_at=check_in, check_out_at=check_out, timezone="UTC")


@pytest.fixture
def service():
    fc._cache.clear()
    svc = TripForecastService(AsyncMock(), AsyncMock())
    svc._client, svc._trips, svc._stays = AsyncMock(), AsyncMock(), AsyncMock()
    svc._trips.get_trip.return_value = SimpleNamespace(start_date=date(2026, 12, 17), end_date=date(2026, 12, 19))
    svc._stays.get_stays.return_value = [_stay(lat=1.0, lng=2.0)]
    svc._client.fetch_range.return_value = {
        "temperature_2m_min": [1, 1, 1], "temperature_2m_max": [4, 4, 4], "precipitation_sum": [0, 5, 0]}
    return svc


@freeze_time("2026-12-10 12:00:00")
class TestService:
    async def test_forecast_for_each_stay_city_using_place_coordinates(self, service):
        result = await service.get_forecast(1)
        assert result.mode == "forecast" and result.available
        assert [d.rain for d in result.cities[0].days] == [False, True, False]
        service._client.geocode.assert_not_awaited()
        assert service._client.fetch_range.await_args.kwargs["archive"] is False

    async def test_each_city_only_gets_the_days_the_trip_is_there(self, service):
        service._stays.get_stays.return_value = [
            _stay("Beta", 1.0, 2.0, datetime(2026, 12, 17, 14), datetime(2026, 12, 18, 10)),
            _stay("Gamma", 3.0, 4.0, datetime(2026, 12, 18, 15), datetime(2026, 12, 19, 10)),
        ]
        result = await service.get_forecast(1)
        days = {c.city: [d.date.day for d in c.days] for c in result.cities}
        assert days == {"Beta": [17, 18], "Gamma": [18, 19]}

    async def test_a_city_in_two_separate_stays_skips_the_days_between(self, service):
        service._stays.get_stays.return_value = [
            _stay("Beta", 1.0, 2.0, datetime(2026, 12, 17, 14), datetime(2026, 12, 17, 20)),
            _stay("Beta", 1.0, 2.0, datetime(2026, 12, 19, 8), datetime(2026, 12, 19, 20)),
        ]
        result = await service.get_forecast(1)
        assert [d.date.day for d in result.cities[0].days] == [17, 19]

    async def test_cities_without_coordinates_are_geocoded_by_name(self, service):
        service._stays.get_stays.return_value = [_stay(lat=None)]
        service._client.geocode.return_value = {"latitude": 3.0, "longitude": 4.0}
        await service.get_forecast(1)
        service._client.geocode.assert_awaited_once_with("Beta, Testland")

    async def test_far_trips_read_the_archive_for_last_year(self, service):
        service._trips.get_trip.return_value = SimpleNamespace(start_date=date(2027, 3, 1), end_date=date(2027, 3, 3))
        service._stays.get_stays.return_value = [_stay(lat=1.0, lng=2.0, check_in=datetime(2027, 3, 1, 14), check_out=datetime(2027, 3, 3, 10))]
        result = await service.get_forecast(1)
        assert result.mode == "climate"
        args = service._client.fetch_range.await_args
        assert args.args[2] == date(2026, 3, 1) and args.kwargs["archive"] is True
        assert result.cities[0].days[0].date == date(2027, 3, 1)

    async def test_weather_service_failure_degrades_to_a_message(self, service):
        service._client.fetch_range.side_effect = RuntimeError("503")
        result = await service.get_forecast(1)
        assert result.available is False and "not available" in result.message

    async def test_no_stays_no_forecast(self, service):
        service._stays.get_stays.return_value = []
        assert (await service.get_forecast(1)).available is False

    async def test_a_second_call_is_served_from_the_cache(self, service):
        await service.get_forecast(1)
        await service.get_forecast(1)
        assert service._client.fetch_range.await_count == 1

    async def test_unknown_and_finished_trips(self, service):
        service._trips.get_trip.return_value = None
        assert await service.get_forecast(9) is None
        service._trips.get_trip.return_value = SimpleNamespace(start_date=date(2026, 11, 1), end_date=date(2026, 11, 2))
        assert (await service.get_forecast(1)).mode == "none"
