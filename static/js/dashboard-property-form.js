window.CIAN_CATEGORIES = {
    rent: [
        { value: 'freeAppointmentObjectRent', label: 'Помещение свободного назначения' },
        { value: 'officeRent', label: 'Офис' },
        { value: 'warehouseRent', label: 'Склад' },
        { value: 'industryRent', label: 'Производство' },
        { value: 'shoppingAreaRent', label: 'Торговая площадь' },
        { value: 'buildingRent', label: 'Здание' },
        { value: 'garageRent', label: 'Гараж' },
        { value: 'commercialLandRent', label: 'Коммерческая земля' }
    ],
    sale: [
        { value: 'freeAppointmentObjectSale', label: 'Помещение свободного назначения' },
        { value: 'officeSale', label: 'Офис' },
        { value: 'warehouseSale', label: 'Склад' },
        { value: 'industrySale', label: 'Производство' },
        { value: 'shoppingAreaSale', label: 'Торговая площадь' },
        { value: 'buildingSale', label: 'Здание' },
        { value: 'garageSale', label: 'Гараж' },
        { value: 'commercialLandSale', label: 'Коммерческая земля' },
        { value: 'businessSale', label: 'Готовый бизнес' }
    ],
    rentToSale: {
        freeAppointmentObjectRent: 'freeAppointmentObjectSale',
        officeRent: 'officeSale',
        warehouseRent: 'warehouseSale',
        industryRent: 'industrySale',
        shoppingAreaRent: 'shoppingAreaSale',
        buildingRent: 'buildingSale',
        garageRent: 'garageSale',
        commercialLandRent: 'commercialLandSale'
    },
    saleToRent: {
        freeAppointmentObjectSale: 'freeAppointmentObjectRent',
        officeSale: 'officeRent',
        warehouseSale: 'warehouseRent',
        industrySale: 'industryRent',
        shoppingAreaSale: 'shoppingAreaRent',
        buildingSale: 'buildingRent',
        garageSale: 'garageRent',
        commercialLandSale: 'commercialLandRent',
        businessSale: 'freeAppointmentObjectRent'
    }
};

(function() {
    var form = document.querySelector('form[action*="/dashboard/properties"]');
    var hidden = document.getElementById('avito_data_json');
    if (!form || !hidden) return;

    var _skipValidation = false;

    form.addEventListener('submit', function(e) {
        if (!_skipValidation) {
            var warnFields = [
                { name: 'building_type', label: 'Тип здания' },
                { name: 'decoration', label: 'Отделка' },
                { name: 'entrance_type', label: 'Вход' },
                { name: 'parking_type', label: 'Парковка' }
            ];
            var missing = [];
            warnFields.forEach(function(f) {
                var el = form.querySelector('select[name="' + f.name + '"]');
                if (el && !el.value) missing.push(f.label);
            });
            if (missing.length) {
                e.preventDefault();
                var old = document.getElementById('validation-warning');
                if (old) old.remove();
                var alert = document.createElement('div');
                alert.id = 'validation-warning';
                alert.className = 'alert alert-warning alert-dismissible fade show mb-3';
                alert.innerHTML =
                    'Рекомендуется заполнить: <strong>' + missing.join(', ') +
                    '</strong> — для корректной выгрузки на Авито и Циан.' +
                    '<div class="mt-2">' +
                    '<button type="button" class="btn btn-sm btn-warning me-2" id="btn-save-anyway">Всё равно сохранить</button>' +
                    '<button type="button" class="btn btn-sm btn-outline-secondary" data-bs-dismiss="alert">Отмена</button>' +
                    '</div>';
                form.parentNode.insertBefore(alert, form);
                alert.scrollIntoView({ behavior: 'smooth', block: 'start' });
                document.getElementById('btn-save-anyway').addEventListener('click', function() {
                    _skipValidation = true;
                    form.requestSubmit();
                });
                return;
            }
        }

        var data = {};
        form.querySelectorAll('.avito-field').forEach(function(el) {
            var key = el.getAttribute('data-key');
            var val = (el.value || '').trim();
            if (key && val) data[key] = val;
        });
        hidden.value = JSON.stringify(data);

        var cianHidden = document.getElementById('cian_data_json');
        if (cianHidden) {
            var cianData = {};
            form.querySelectorAll('.cian-field').forEach(function(el) {
                var key = el.getAttribute('data-key');
                var val = (el.value || '').trim();
                if (key) cianData[key] = val;
            });
            cianHidden.value = JSON.stringify(cianData);
        }

        var gallery = document.getElementById('unified-gallery');
        var orderInput = document.getElementById('gallery-order-input');
        if (gallery && orderInput) {
            var items = gallery.querySelectorAll('.gallery-item');
            var order = [];
            var newIdx = 0;
            items.forEach(function(el) {
                if (el.dataset.type === 'existing') {
                    order.push('existing:' + el.dataset.imageId);
                } else if (el.dataset.type === 'new') {
                    order.push('new:' + newIdx);
                    newIdx++;
                }
            });
            orderInput.value = order.join(',');
        }
    });

    function toggleAvitoByDealType() {
        var sel = form.querySelector('select[name="deal_type"]');
        var isRent = sel && sel.value === 'Аренда';
        var rentReq = document.getElementById('avito-required-rent');
        var saleReq = document.getElementById('avito-required-sale');
        var rentBlock = document.getElementById('avito-block-rent');
        var saleBlock = document.getElementById('avito-block-sale');
        if (rentReq) rentReq.style.display = isRent ? 'block' : 'none';
        if (saleReq) saleReq.style.display = isRent ? 'none' : 'block';
        if (rentBlock) rentBlock.style.display = isRent ? 'block' : 'none';
        if (saleBlock) saleBlock.style.display = isRent ? 'none' : 'block';
        var cianRent = document.getElementById('cian-rent-type');
        var cianSale = document.getElementById('cian-sale-type');
        var cianRights = document.getElementById('cian-property-rights');
        var cianPaymentWrap = document.getElementById('cian-payment-period-wrap');
        var cianLeaseWrap = document.getElementById('cian-lease-type-wrap');
        var cianContractWrap = document.getElementById('cian-contract-type-wrap');
        if (cianRent) cianRent.style.display = isRent ? 'block' : 'none';
        if (cianSale) cianSale.style.display = isRent ? 'none' : 'block';
        if (cianRights) cianRights.style.display = isRent ? 'none' : 'block';
        if (cianPaymentWrap) cianPaymentWrap.style.display = isRent ? 'block' : 'none';
        if (cianLeaseWrap) cianLeaseWrap.style.display = isRent ? 'block' : 'none';
        if (cianContractWrap) cianContractWrap.style.display = isRent ? 'none' : 'block';
        var catSelect = document.getElementById('cian-category-select');
        if (catSelect && window.CIAN_CATEGORIES) {
            var cur = (catSelect.value || '').trim();
            var opts = isRent ? window.CIAN_CATEGORIES.rent : window.CIAN_CATEGORIES.sale;
            var map = isRent ? window.CIAN_CATEGORIES.saleToRent : window.CIAN_CATEGORIES.rentToSale;
            catSelect.options.length = 0;
            opts.forEach(function(o) {
                var opt = new Option(o.label, o.value);
                catSelect.options.add(opt);
            });
            var newVal = map[cur] || (isRent ? 'freeAppointmentObjectRent' : 'freeAppointmentObjectSale');
            catSelect.value = newVal;
        }
    }

    if (form && form.querySelector('select[name="deal_type"]')) {
        form.querySelector('select[name="deal_type"]').addEventListener('change', toggleAvitoByDealType);
        toggleAvitoByDealType();
    }
})();

