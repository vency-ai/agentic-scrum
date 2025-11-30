  kubectl create secret docker-registry agile-corp-reg-secret \
      --namespace=dsm \
      --docker-server=myreg.agile-corp.org:5000 \
      --docker-username="reg-user" \
      --docker-password="reg@user123" \
      --docker-email=test@test.com
